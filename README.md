# 金沢サークルハブ　サークル宣伝 X bot

## 概要
金沢サークルハブのXアカウントで、DB上の認証済みサークルをランダムに宣伝するbot。

## 構成
### 使用言語
- Python
### ホスティング
- Github
- Github Actionsによる定期実行
### データベース
- Supabase

## DB構成

- `clubs`: サークルの名前(name)、slug、プロフィール画像のURL(profile_image_url)などを格納するテーブル
- `is_verified`: 金沢サークルハブ認証済みサークルのclub_idを格納するテーブル
- `club_infos`: club_id、団体概要(description)などを格納するテーブル


## フロー
1. Supabase APIを叩き、clubsテーブルのレコードを全て取得。
2. is_verifiedテーブルのレコードを全て取得。
3. 取得したclubsのうち、club_idが存在するレコードのみに絞り込む。--> verified_clubsと定義
4. 乱数により、verified_clubsから1つのレコードを取り出す。--> selected_clubと定義
5. club_infosテーブルから、club_idがselected_clubに対応するレコードを取り出す。--> selected_club_infoと定義
6. selected_clubとselected_club_infoを結合
7. 投稿文を作成 --> msgと定義
8. XのAPIを叩き、msgをXに投稿する

## 投稿文テンプレート
日付のフォーマットを整え、ハッシュタグを追加することで、より多くのユーザーに投稿が届きやすくなります。

```python
from datetime import datetime

today_str = datetime.now().strftime('%Y/%m/%d')

text = f"""--サークル紹介 {today_str}--\n
【{ selected_club.name }】\n
{ selected_club_info.description }\n\n
詳細はこちらをチェック！\n
https://kanazawa-circle-hub.vercel.app/clubs/{ selected_club.slug }\n\n

 #金沢大学 #サークル #春から金大
"""

image_url = selected_club.profile_image_url
```

## 開発
### 環境変数
.envファイルを作成。