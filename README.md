# Myanmar Bots

Three bots for the user's businesses, deployed on Railway as separate services
from this monorepo (set each service's Root Directory accordingly).

| Folder             | Service type | What it is                                  |
|--------------------|--------------|---------------------------------------------|
| `telegram-bot/`    | worker       | MasterClass English Telegram FAQ bot        |
| `subscription-bot/`| worker       | Biggest Seller Myanmar Telegram catalog bot |
| `messenger-bots/`  | web          | Messenger webhooks for both businesses      |

Each folder has its own `requirements.txt` and `Procfile`.
See each folder's README for setup and environment variables.
