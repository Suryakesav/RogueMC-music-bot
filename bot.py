"""A small, self-hosted Discord music bot."""

from __future__ import annotations

import asyncio
import logging
import os
from collections import deque
from dataclasses import dataclass
from typing import Deque

import discord
import yt_dlp
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("free-music-bot")

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("Set DISCORD_TOKEN in your .env file. See README.md.")

YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch1",
    "source_address": "0.0.0.0",
}
FFMPEG_BEFORE_OPTIONS = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
FFMPEG_OPTIONS = "-vn"


@dataclass
class Track:
    title: str
    webpage_url: str
    stream_url: str
    requester: str


def extract_track(query: str, requester: str) -> Track:
    """Resolve a URL or a search phrase to one playable audio stream."""
    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        info = ydl.extract_info(query, download=False)
    if "entries" in info:
        info = next((entry for entry in info["entries"] if entry), None)
    if not info or not info.get("url"):
        raise ValueError("I couldn't find a playable result for that request.")
    return Track(
        title=info.get("title") or "Unknown track",
        webpage_url=info.get("webpage_url") or query,
        stream_url=info["url"],
        requester=requester,
    )


class GuildPlayer:
    def __init__(self, guild: discord.Guild):
        self.guild = guild
        self.loop = asyncio.get_running_loop()
        self.queue: Deque[Track] = deque()
        self.current: Track | None = None
        self.next_track = asyncio.Event()
        self.task: asyncio.Task | None = None
        self.text_channel_id: int | None = None

    def start(self) -> None:
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._player_loop())

    async def _player_loop(self) -> None:
        while True:
            self.next_track.clear()
            if not self.queue:
                self.current = None
                try:
                    await asyncio.wait_for(self.next_track.wait(), timeout=180)
                except asyncio.TimeoutError:
                    voice = self.guild.voice_client
                    if voice and not voice.is_playing() and not self.queue:
                        await voice.disconnect()
                    return
                continue

            self.current = self.queue.popleft()
            voice = self.guild.voice_client
            if not voice or not voice.is_connected():
                self.current = None
                return

            try:
                source = discord.FFmpegPCMAudio(
                    self.current.stream_url,
                    before_options=FFMPEG_BEFORE_OPTIONS,
                    options=FFMPEG_OPTIONS,
                )
                voice.play(source, after=lambda error: self._after_track(error))
            except Exception:
                log.exception("Could not start audio playback")
                self.next_track.set()
                continue

            channel = self.guild.get_channel(self.text_channel_id) if self.text_channel_id else None
            if channel:
                await channel.send(f"🎶 Now playing **{discord.utils.escape_markdown(self.current.title)}**")
            await self.next_track.wait()

    def _after_track(self, error: Exception | None) -> None:
        if error:
            log.warning("Audio playback ended with an error: %s", error)
        self.loop.call_soon_threadsafe(self.next_track.set)


intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
players: dict[int, GuildPlayer] = {}


def player_for(guild: discord.Guild) -> GuildPlayer:
    return players.setdefault(guild.id, GuildPlayer(guild))


async def voice_for(interaction: discord.Interaction) -> discord.VoiceClient:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        raise app_commands.AppCommandError("Use this command in a server.")
    if not interaction.user.voice or not interaction.user.voice.channel:
        raise app_commands.AppCommandError("Join a voice channel first.")
    voice = interaction.guild.voice_client
    if voice is None:
        voice = await interaction.user.voice.channel.connect()
    elif voice.channel != interaction.user.voice.channel:
        raise app_commands.AppCommandError("Join the voice channel where I’m playing music.")
    return voice


@bot.event
async def on_ready() -> None:
    try:
        synced = await bot.tree.sync()
        log.info("Signed in as %s; synced %d slash commands", bot.user, len(synced))
    except Exception:
        log.exception("Could not sync slash commands")


@bot.tree.command(name="play", description="Play a song by search phrase or supported audio URL")
@app_commands.describe(query="Song title or URL")
async def play(interaction: discord.Interaction, query: str) -> None:
    await interaction.response.defer(thinking=True)
    try:
        voice = await voice_for(interaction)
        track = await asyncio.to_thread(extract_track, query, interaction.user.display_name)
        player = player_for(interaction.guild)
        player.text_channel_id = interaction.channel_id
        player.queue.append(track)
        player.start()
        position = len(player.queue) + (1 if player.current else 0)
        await interaction.followup.send(
            f"Added **{discord.utils.escape_markdown(track.title)}** to the queue (position {position}).\n{track.webpage_url}"
        )
    except Exception as error:
        await interaction.followup.send(f"Couldn't play that request: {error}", ephemeral=True)


@bot.tree.command(name="queue", description="Show the current song and upcoming tracks")
async def show_queue(interaction: discord.Interaction) -> None:
    if not interaction.guild:
        await interaction.response.send_message("Use this command in a server.", ephemeral=True)
        return
    player = players.get(interaction.guild.id)
    if not player or (not player.current and not player.queue):
        await interaction.response.send_message("The queue is empty.")
        return
    lines = []
    if player.current:
        lines.append(f"**Now playing:** {discord.utils.escape_markdown(player.current.title)}")
    for index, track in enumerate(list(player.queue)[:10], start=1):
        lines.append(f"{index}. {discord.utils.escape_markdown(track.title)}")
    if len(player.queue) > 10:
        lines.append(f"…and {len(player.queue) - 10} more")
    await interaction.response.send_message("\n".join(lines))


@bot.tree.command(name="skip", description="Skip the current song")
async def skip(interaction: discord.Interaction) -> None:
    if not interaction.guild or not interaction.guild.voice_client or not interaction.guild.voice_client.is_playing():
        await interaction.response.send_message("Nothing is playing right now.", ephemeral=True)
        return
    interaction.guild.voice_client.stop()
    await interaction.response.send_message("Skipped.")


@bot.tree.command(name="pause", description="Pause the current song")
async def pause(interaction: discord.Interaction) -> None:
    voice = interaction.guild.voice_client if interaction.guild else None
    if voice and voice.is_playing():
        voice.pause()
        await interaction.response.send_message("Paused.")
    else:
        await interaction.response.send_message("Nothing is playing right now.", ephemeral=True)


@bot.tree.command(name="resume", description="Resume the paused song")
async def resume(interaction: discord.Interaction) -> None:
    voice = interaction.guild.voice_client if interaction.guild else None
    if voice and voice.is_paused():
        voice.resume()
        await interaction.response.send_message("Resumed.")
    else:
        await interaction.response.send_message("Nothing is paused right now.", ephemeral=True)


@bot.tree.command(name="stop", description="Stop playback and clear the queue")
async def stop(interaction: discord.Interaction) -> None:
    if not interaction.guild:
        await interaction.response.send_message("Use this command in a server.", ephemeral=True)
        return
    player = players.get(interaction.guild.id)
    if player:
        player.queue.clear()
        player.current = None
    voice = interaction.guild.voice_client
    if voice and (voice.is_playing() or voice.is_paused()):
        voice.stop()
    await interaction.response.send_message("Stopped playback and cleared the queue.")


@bot.tree.command(name="leave", description="Clear the queue and leave the voice channel")
async def leave(interaction: discord.Interaction) -> None:
    if not interaction.guild:
        await interaction.response.send_message("Use this command in a server.", ephemeral=True)
        return
    player = players.pop(interaction.guild.id, None)
    if player:
        player.queue.clear()
        player.current = None
    voice = interaction.guild.voice_client
    if voice:
        await voice.disconnect()
    await interaction.response.send_message("Left the voice channel.")


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    message = str(error)
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


bot.run(TOKEN)
