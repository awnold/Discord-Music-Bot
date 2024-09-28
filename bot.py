import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

# Retrieve the Discord token from environment variables
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="m-", intents=intents)

# Music queue for each server
queues = {}

# Role name for permission to /skip, /pause, and /resume (Default: "DJ")
DJ_ROLE_NAME = "DJ"

# Options for yt-dlp
yt_dlp_options = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',  # We bind to IPv4 here since IPv6 addresses can cause issues sometimes
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',  # 192 kbps
    }]
}

yt_dlp_handler = yt_dlp.YoutubeDL(yt_dlp_options)

# FFmpeg options for improved audio quality
ffmpeg_options = {
    'options': '-vn -ar 48000 -ac 2 -b:a 192k'  # 48kHz, stereo, 192kbps bitrate
}

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: yt_dlp_handler.extract_info(url, download=False))
        if 'entries' in data:
            data = data['entries'][0]
        filename = data['url']
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} ({bot.user.id})")


async def play_next_in_queue(ctx):
    if queues[ctx.guild.id]:
        next_song = queues[ctx.guild.id].pop(0)
        embed = discord.Embed(
            title="Now Playing",
            description=f"[{next_song['title']}]({next_song['url']})",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)
        player = await YTDLSource.from_url(next_song['url'], loop=bot.loop)
        ctx.voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next_in_queue(ctx), bot.loop))


@bot.command(name="join")
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send(f"Joined {channel}")
    else:
        await ctx.send("You need to be in a voice channel first!")


@bot.command(name="play")
async def play(ctx, *, url):
    if ctx.voice_client is None:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            await ctx.send("You need to be in a voice channel first!")
            return

    async with ctx.typing():
        player = await YTDLSource.from_url(url, loop=bot.loop)
        song_info = {"title": player.title, "url": url}

        if ctx.guild.id not in queues:
            queues[ctx.guild.id] = []

        if ctx.voice_client.is_playing():
            queues[ctx.guild.id].append(song_info)
            await ctx.send(f"Added to queue: {player.title}")
        else:
            ctx.voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next_in_queue(ctx), bot.loop))
            embed = discord.Embed(
                title="Now Playing",
                description=f"[{player.title}]({url})",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)


@bot.command(name="np", aliases=["nowplaying", "playing", "currentsong", "current"])
async def np(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        current_song = ctx.voice_client.source.data
        embed = discord.Embed(
            title="Now Playing",
            description=f"[{current_song['title']}]({current_song['url']})",
            color=discord.Color.purple()
        )
        await ctx.send(embed=embed)
    else:
        await ctx.send("No music is currently playing.")


@bot.command(name="skip")
@commands.has_role(DJ_ROLE_NAME)
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("Skipped the current song!")
    else:
        await ctx.send("No music is playing right now.")


@bot.command(name="queue")
async def queue(ctx):
    if ctx.guild.id in queues and queues[ctx.guild.id]:
        queue_list = "\n".join([f"{i+1}. {song['title']}" for i, song in enumerate(queues[ctx.guild.id])])
        await ctx.send(f"Current queue:\n{queue_list}")
    else:
        await ctx.send("The queue is currently empty.")


@bot.command(name="pause")
@commands.has_role(DJ_ROLE_NAME)
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("Music paused.")
    else:
        await ctx.send("No music is currently playing.")


@bot.command(name="resume")
@commands.has_role(DJ_ROLE_NAME)
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("Music resumed.")
    else:
        await ctx.send("No music is currently paused.")


@bot.command(name="leave")
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Disconnected from the voice channel.")
    else:
        await ctx.send("I'm not in a voice channel!")


# Error handling
@skip.error
async def skip_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send(f"You need the {DJ_ROLE_NAME} role to skip songs.")

@pause.error
async def pause_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send(f"You need the {DJ_ROLE_NAME} role to pause the music.")

@resume.error
async def resume_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send(f"You need the {DJ_ROLE_NAME} role to resume the music.")


# Start the bot with the token from environment variables
bot.run(DISCORD_TOKEN)
