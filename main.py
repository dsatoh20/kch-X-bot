import os
import io
import random
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from supabase import create_client, Client
from postgrest import APIError
import tweepy

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY")
TWITTER_CONSUMER_KEY = os.environ.get("TWITTER_CONSUMER_KEY")
TWITTER_CONSUMER_SECRET = os.environ.get("TWITTER_CONSUMER_SECRET")
TWITTER_ACCESS_TOKEN = os.environ.get("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET")
BASE_URL = os.environ.get("BASE_URL")

JST = timezone(timedelta(hours=9))
TWEET_LIMIT = 280

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    client_v2 = tweepy.Client(
        consumer_key=TWITTER_CONSUMER_KEY,
        consumer_secret=TWITTER_CONSUMER_SECRET,
        access_token=TWITTER_ACCESS_TOKEN,
        access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
    )
    api_v1 = tweepy.API(tweepy.OAuth1UserHandler(
        consumer_key=TWITTER_CONSUMER_KEY,
        consumer_secret=TWITTER_CONSUMER_SECRET,
        access_token=TWITTER_ACCESS_TOKEN,
        access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
    ))
except Exception as e:
    print(f"エラー: クライアントの初期化に失敗しました。 - {e}")
    exit()


def get_random_club():
    try:
        clubs_response = supabase.table('clubs').select('id, name, slug, profile_image_url').execute()
        verified_response = supabase.table('is_verified').select('club_id').execute()

        if not clubs_response.data or not verified_response.data:
            print("エラー: DBからデータを取得できませんでした。")
            return None

        verified_ids = {item['club_id'] for item in verified_response.data}
        verified_clubs = [c for c in clubs_response.data if c['id'] in verified_ids]

        if not verified_clubs:
            print("エラー: 認証済みサークルが見つかりませんでした。")
            return None

        club = random.choice(verified_clubs)
        print(f"選択: {club['name']} (ID: {club['id']})")

        info_response = (
            supabase.table('club_infos')
            .select('description')
            .eq('club_id', club['id'])
            .limit(1)
            .single()
            .execute()
        )
        description = (info_response.data or {}).get('description') or "(自己紹介文がありません)"

        return {
            "name": club['name'],
            "slug": club['slug'],
            "profile_image_url": club.get('profile_image_url'),
            "description": description,
        }

    except APIError as e:
        print(f"エラー: Supabase API - {e}")
        return None
    except Exception as e:
        print(f"エラー: サークル情報の取得中に予期せぬエラーが発生しました。 - {e}")
        return None


def create_post_text(club_data):
    timestamp_str = datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S')

    header = f"--サークル紹介--\n\n【{club_data['name']}】\n"
    footer = f"\n詳細はブラウザからチェック！\n\n#金沢大学 #サークル #春から金大\n\n({timestamp_str})\n"
    description_limit = TWEET_LIMIT - len(header) - len(footer)

    description = club_data['description']
    if len(description) > description_limit:
        description = description[:description_limit - 1] + "…"
        print(f"警告: descriptionを{description_limit}文字に切り詰めました。")

    return header + description + footer


def post_to_x(text, image_url):
    media_id = None
    try:
        if image_url:
            response = requests.get(image_url, stream=True)
            response.raise_for_status()
            print("メディアをアップロード中...")
            media = api_v1.media_upload(filename="image.jpg", file=io.BytesIO(response.content))
            media_id = media.media_id
            print(f"メディアアップロード成功 (media_id: {media_id})")

        print("ツイートを投稿中...")
        client_v2.create_tweet(text=text, media_ids=[media_id] if media_id else None)
        print("ツイートの投稿に成功しました。")

    except tweepy.errors.Forbidden as e:
        print(f"エラー: 投稿が拒否されました(403 Forbidden)。 - {e}")
    except requests.exceptions.RequestException as e:
        print(f"警告: 画像のダウンロードに失敗しました。テキストのみで投稿します。 - {e}")
        try:
            client_v2.create_tweet(text=text)
            print("テキストのみでの投稿に成功しました。")
        except Exception as e_tweet:
            print(f"エラー: テキストのみの投稿にも失敗しました。 - {e_tweet}")
    except Exception as e:
        print(f"エラー: ツイートの投稿中に予期せぬエラーが発生しました。 - {e}")


def main():
    print(f"処理を開始します... ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

    club = get_random_club()
    if not club:
        print("処理を終了します。")
        return

    post_to_x(create_post_text(club), club.get('profile_image_url'))
    print("処理が完了しました。")


if __name__ == "__main__":
    main()
