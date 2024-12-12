import discord
from discord.ext import commands
from gtts import gTTS
import io
import asyncio
from collections import deque
import os

# Set up intents
intents = discord.Intents.default()
intents.voice_states = True
intents.guilds = True
intents.members = True
intents.message_content = True

# Create bot instance
bot = commands.Bot(command_prefix="!", intents=intents)

# Global variables
language = "ro"  # Default language
audio_queue = deque()  # Queue for managing audio tasks
is_playing = False  # Flag to indicate if audio is currently playing
include_username = False  # Default is to not include username


@bot.event
async def on_ready():
    print(f"Bot is ready as {bot.user}")

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return

    global language
    event_message = None

    # Detect join, leave, and deafened events
    if before.channel is None and after.channel is not None:
        event_message = f"{member.name} has joined."
    elif before.channel is not None and after.channel is None:
        event_message = f"{member.name} has left."
    elif before.self_deaf != after.self_deaf:
        if after.self_deaf:
            event_message = f"{member.name} has deafened."
        else:
            event_message = f"{member.name} has undeafened."

    if event_message:
        print(event_message)
        # Add the event message to the queue
        await enqueue_audio(member.guild, event_message)

async def enqueue_audio(guild, text, filename=None):
    """Add a message or MP3 file to the audio queue."""
    global audio_queue, is_playing

    if filename:
        # If an MP3 file is provided, enqueue it directly
        audio_queue.append((guild, filename, "file"))
    else:
        # Generate TTS audio for the text message
        tts = gTTS(text=text, lang="en")
        mp3_fp = io.BytesIO()
        tts.write_to_fp(mp3_fp)
        mp3_fp.seek(0)
        audio_queue.append((guild, mp3_fp, "stream"))

    # Start playing if not already playing
    if not is_playing:
        await play_next_audio()

async def play_next_audio():
    """Play the next audio in the queue."""
    global audio_queue, is_playing

    if len(audio_queue) == 0:
        is_playing = False
        return

    is_playing = True
    guild, audio_source, source_type = audio_queue.popleft()

    # Ensure the bot is connected to a voice channel
    if not guild.voice_client:
        print("Bot is not connected to a voice channel.")
        is_playing = False
        return

    # Play the audio based on its type
    if source_type == "file":
        guild.voice_client.play(
            discord.FFmpegPCMAudio(audio_source),
            after=lambda e: asyncio.run_coroutine_threadsafe(play_next_audio(), bot.loop),
        )
    elif source_type == "stream":
        guild.voice_client.play(
            discord.FFmpegPCMAudio(audio_source, pipe=True),
            after=lambda e: asyncio.run_coroutine_threadsafe(play_next_audio(), bot.loop),
        )

@bot.command(name="toggleuser")
async def toggle_user(ctx):
    """Toggle whether the username is included in the spoken message."""
    global include_username
    include_username = not include_username
    status = "enabled" if include_username else "disabled"
    await ctx.send(f"Username inclusion in messages has been `{status}`.")


@bot.command(name="queue")
async def show_queue(ctx):
    if not audio_queue:
        await ctx.send("The queue is currently empty.")
    else:
        queue_list = "\n".join([f"{i+1}. {item[1]}" for i, item in enumerate(audio_queue)])
        await ctx.send(f"Current Queue:\n{queue_list}")



@bot.command(name="speak")
async def speak(ctx, *, text: str):
    """Command to speak a custom message and save it as an MP3 file."""
    global language, include_username

    # Ensure the bot is connected to a voice channel
    if not ctx.voice_client:
        if ctx.author.voice:
            channel = ctx.author.voice.channel
            await channel.connect()
        else:
            await ctx.send("You need to be in a voice channel for me to join and play audio!")
            return

    # Format the message based on the toggle
    if include_username:
        message = f"{ctx.author.name} a spus, {text}" if language == "ro" else f"{ctx.author.name} said, {text}"
    else:
        message = text

    try:
        # Generate the MP3 file
        filename = f"{ctx.author.id}_{int(ctx.message.created_at.timestamp())}.mp3"
        tts = gTTS(text=message, lang=language)
        tts.save(filename)

        # Add the MP3 file to the queue
        await enqueue_audio(ctx.guild, message, filename)

        # Send the MP3 file to the text channel
        with open(filename, "rb") as file:
            await ctx.send("Your message has been added to the queue and saved as an MP3 file:", file=discord.File(file, filename=filename))

        # Cleanup (delete the file after sending)
        os.remove(filename)
    except Exception as e:
        #await ctx.send("Failed to process the command.")
        print(f"Error in speak command: {e}")


@bot.command(name="join")
async def join(ctx):
    """Command to join the user's voice channel."""
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        if not ctx.voice_client or not ctx.voice_client.is_connected():
            await channel.connect()
            await ctx.send(f"Joined {channel.name}!")
        else:
            await ctx.send("I'm already in a voice channel!")
    else:
        await ctx.send("You need to be in a voice channel for me to join!")

@bot.command(name="leave")
async def leave(ctx):
    """Command to leave the current voice channel."""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Disconnected from the voice channel!")
        global audio_queue, is_playing
        audio_queue.clear()  # Clear the queue when leaving
        is_playing = False
    else:
        await ctx.send("I'm not in a voice channel!")

@bot.command(name="setlang")
async def set_language(ctx, lang: str):
    """Command to set the language for TTS."""
    global language
    try:
        # Test if the language is supported by gTTS
        gTTS(text="Test", lang=lang)
        language = lang
        await ctx.send(f"Language has been set to `{lang}`.")
    except ValueError:
        await ctx.send(f"Invalid language code: `{lang}`. Please provide a valid language code (e.g., 'en', 'ro').")


bot.run(os.getenv("DISCORD_BOT_TOKEN"))
