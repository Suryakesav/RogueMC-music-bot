# RogueMC musicBOT

A free, self-hosted Discord music bot with slash commands for playing music, managing a queue, and controlling playback.

## Commands

- `/play query` — search for a song or paste a supported audio URL
- `/queue` — show the current track and upcoming tracks
- `/skip` — skip the current track
- `/pause` and `/resume` — control playback
- `/stop` — stop playback and clear the queue
- `/leave` — clear the queue and leave voice

The bot searches one result for a plain-text query. It streams audio through yt-dlp and FFmpeg. Use sources you are allowed to access and play; source sites may restrict automated playback, and their terms apply.

## Requirements

- Python 3.10 or newer
- FFmpeg installed and available as `ffmpeg` on your PATH
- A Discord application with a bot user

## Create and invite the Discord bot

1. In the [Discord Developer Portal](https://discord.com/developers/applications), create an application and add a bot user.
2. Copy the bot token. Keep it private; do not post it in chat or commit it to Git.
3. Under **Installation** (or **OAuth2 → URL Generator**), select the `bot` and `applications.commands` scopes. Grant `View Channels`, `Send Messages`, `Connect`, and `Speak` permissions, then open the generated install URL and add the bot to your server.
4. In this folder, copy `.env.example` to `.env` and put the token after `DISCORD_TOKEN=`.

## Run it

From this folder, create a virtual environment, install the dependencies, then start the bot:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python bot.py
```

Keep the process running while you use the bot. This project has no subscription or paid hosting requirement; a computer or server must stay online for the bot to respond.

## Put the code on GitHub and keep the bot online

GitHub stores the bot's code; it does not keep a Discord bot connected 24/7. To use GitHub as part of the setup:

1. Create a **private** repository on GitHub.
2. Upload the files in this folder. Do **not** upload `.env`; `.gitignore` excludes it. Never put the bot token in `bot.py`, README files, or GitHub source code.
3. Choose a host that can run a long-lived Python worker and install FFmpeg. Connect that host to the GitHub repository.
4. Set the install command to `pip install -r requirements.txt` and the start command to `python bot.py`.
5. In the host's environment-variable settings, add `DISCORD_TOKEN` with your Discord bot token. Do not put the token in a GitHub Actions workflow or commit it to the repository.
6. Deploy. The host must keep the process running; a free plan that sleeps or stops background workers will make the bot go offline.

You can also run it locally with the steps above and push code changes to GitHub when you want to save them. GitHub Actions is designed for short jobs and is not a reliable way to keep a voice bot connected continuously.

## Notes

- Slash commands sync when the bot starts. It can take a short while for Discord to show newly registered commands.
- The bot joins the voice channel of the person who runs `/play`.
- If audio does not start, confirm FFmpeg is installed, the bot has Connect and Speak permission, and the source is reachable.
