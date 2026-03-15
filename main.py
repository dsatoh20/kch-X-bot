import os
import requests
import io
import random
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from supabase import create_client, Client
from postgrest import APIError
import tweepy

# .envファイルから環境変数を読み込む
load_dotenv()

# --- 環境変数 (READMEの「開発」セクションを参照) ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY")
TWITTER_CONSUMER_KEY = os.environ.get("TWITTER_CONSUMER_KEY")
TWITTER_CONSUMER_SECRET = os.environ.get("TWITTER_CONSUMER_SECRET")
TWITTER_ACCESS_TOKEN = os.environ.get("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET")
BASE_URL = os.environ.get("BASE_URL") # 金沢サークルハブのサイトURL


# --- クライアントの初期化 ---
try:
    # Supabaseクライアント
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Twitter API v2クライアント (ツイート作成用)
    client_v2 = tweepy.Client(
        consumer_key=TWITTER_CONSUMER_KEY,
        consumer_secret=TWITTER_CONSUMER_SECRET,
        access_token=TWITTER_ACCESS_TOKEN,
        access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
    )
    # Twitter API v1.1クライアント (メディアアップロード用)
    auth_v1 = tweepy.OAuth1UserHandler(
        consumer_key=TWITTER_CONSUMER_KEY,
        consumer_secret=TWITTER_CONSUMER_SECRET,
        access_token=TWITTER_ACCESS_TOKEN,
        access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
    )
    api_v1 = tweepy.API(auth_v1)

except Exception as e:
    print(f"エラー: 環境変数の設定またはクライアントの初期化に失敗しました。 - {e}")
    exit()


def get_random_club_from_readme_flow():
    """
    README.mdに記載されたフローに従い、サークル情報を取得・結合する。
    NOTE: この方法は複数回のAPI呼び出しとクライアントサイドでのデータ処理を
          行うため、データ量が増えると非効率になる可能性があります。
          DB側でJOINとランダム選択を行うRPC関数を実装する方が効率的です。
    """
    try:
        # 1 & 2. clubsとis_verifiedテーブルからデータを取得
        print("DBからサークルリストと認証済みIDを取得します...")
        clubs_response = supabase.table('clubs').select('id, name, slug, profile_image_url').execute()
        verified_response = supabase.table('is_verified').select('club_id').execute()

        if not clubs_response.data or not verified_response.data:
            print("エラー: 'clubs'または'is_verified'テーブルからデータを取得できませんでした。")
            return None

        all_clubs = {club['id']: club for club in clubs_response.data}
        verified_club_ids = {item['club_id'] for item in verified_response.data}

        # 3. 認証済みサークルに絞り込む
        verified_clubs_list = [
            club for club_id, club in all_clubs.items() if club_id in verified_club_ids
        ]

        if not verified_clubs_list:
            print("エラー: 処理対象の認証済みサークルが見つかりませんでした。")
            return None

        # 4. ランダムに1つ選択
        selected_club = random.choice(verified_clubs_list)
        selected_club_id = selected_club['id']
        print(f"ランダムにサークルを選択しました: {selected_club['name']} (ID: {selected_club_id})")

        # 5. club_infosテーブルから詳細情報を取得
        print("サークルの詳細情報を取得します...")
        info_response = supabase.table('club_infos').select('description').eq('club_id', selected_club_id).limit(1).single().execute()

        # 6. 取得した情報を結合
        description = "(詳細情報がありません)"
        if info_response.data and 'description' in info_response.data:
            description = info_response.data['description']
        else:
            print(f"警告: club_id {selected_club_id} の詳細情報(description)が見つかりませんでした。")

        # 最終的な辞書を作成して返す
        final_club_data = {
            "name": selected_club['name'],
            "slug": selected_club['slug'],
            "profile_image_url": selected_club.get('profile_image_url'),
            "description": description
        }
        return final_club_data

    except APIError as e:
        print(f"エラー: Supabase APIとの通信でエラーが発生しました。 - {e}")
        print("ヒント: APIキーが正しいか、テーブルのRow Level Security(RLS)設定で'anon'キーからのSELECTが許可されているか確認してください。")
        return None
    except Exception as e:
        # ネットワークエラーや予期せぬエラー
        print(f"エラー: サークル情報の取得・結合処理中に予期せぬエラーが発生しました。 - {e}")
        return None


def create_post_text(club_data):
    """投稿用のテキストを生成する"""
    # JST (UTC+9) のタイムゾーンを定義
    jst_tz = timezone(timedelta(hours=9))
    # 現在のJSTでの日時を取得し、重複投稿を避けるために時刻まで含める
    timestamp_str = datetime.now(jst_tz).strftime('%Y-%m-%d %H:%M:%S')

    # 投稿用のURLを生成
    club_url = f"{BASE_URL}/club/{club_data['slug']}"

    # READMEのテンプレートを基にテキストを生成
    text = f"""--サークル紹介--

【{club_data['name']}】
{club_data['description']}

詳細はこちらをチェック！
{club_url}

#金沢大学 #サークル #春から金大

({timestamp_str})
"""
    return text


def post_to_x(text, image_url):
    """テキストと画像をXに投稿する"""
    media_id = None
    try:
        # 画像URLがあれば画像をダウンロードしてアップロード
        if image_url:
            response = requests.get(image_url, stream=True)
            response.raise_for_status()  # HTTPエラーがあれば例外を発生

            # 画像データをメモリ上でファイルのように扱う
            image_data = io.BytesIO(response.content)
            # Tweepy v1.1のmedia_uploadはファイル名が必須引数だが、
            # file引数にファイルライクオブジェクトを渡せる
            media = api_v1.media_upload(filename="image.jpg", file=image_data)
            media_id = media.media_id

        # ツイートを投稿
        client_v2.create_tweet(text=text, media_ids=[media_id] if media_id else None)
        print("ツイートの投稿に成功しました。")

    except tweepy.errors.Forbidden as e:
        print(f"エラー: Twitter APIへの投稿が拒否されました(403 Forbidden)。 - {e}")
        print("ヒント: Twitter Developer Appのパーミッションが'Read and Write'になっているか、APIキー/トークンが正しいか確認してください。")

    except requests.exceptions.RequestException as e:
        print(f"警告: 画像のダウンロードに失敗しました。テキストのみで投稿を試みます。 - {e}")
        try:
            # 画像なしでテキストのみ投稿
            client_v2.create_tweet(text=text)
            print("テキストのみでのツイート投稿に成功しました。")
        except Exception as e_tweet:
            print(f"エラー: テキストのみのツイート投稿にも失敗しました。 - {e_tweet}")
    except Exception as e:
        print(f"エラー: ツイートの投稿中に予期せぬエラーが発生しました。 - {e}")


def main():
    """メイン処理"""
    print(f"処理を開始します... ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

    # 1. ランダムなサークルを取得 (READMEのフローに従う)
    selected_club = get_random_club_from_readme_flow()
    if not selected_club:
        print("処理を終了します。")
        return

    # 2. 投稿文を作成
    post_text = create_post_text(selected_club)

    # 3. Xに投稿
    post_to_x(post_text, selected_club.get('profile_image_url'))

    print("処理が完了しました。")


if __name__ == "__main__":
    main()
