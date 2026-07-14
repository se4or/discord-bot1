import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import datetime, timedelta
import json
import os
from dotenv import load_dotenv
import random
import aiohttp
import pytz
import re

# Load environment variables
load_dotenv()

# Debug: Print if token was loaded
if not os.getenv('DISCORD_TOKEN'):
    print("ERROR: DISCORD_TOKEN not found in environment variables!")
    print(f"Current working directory: {os.getcwd()}")
    print(f"Looking for .env file at: {os.path.join(os.getcwd(), '.env')}")
    print(f".env file exists: {os.path.exists('.env')}")
    exit(1)

# Bot setup
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=',', intents=intents, help_command=None)

# Storage for AFK users
afk_users = {}  # {user_id: {'reason': 'reason', 'original_nick': 'nick'}}

# Storage for user timezones
user_timezones = {}  # {user_id: 'timezone_string'}

# ==================== AI Chat Setup (Google Gemini, free tier) ====================

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent"

# Per-user chat history: {user_id: [("user"|"model", text), ...]}
chat_histories = {}
MAX_HISTORY_TURNS = 20  # keep the last 20 messages (both sides combined)

CHAT_SYSTEM_PROMPT = (
    "You are a witty, casual Discord bot chatting with a friend. Keep replies "
    "concise (usually 1-4 sentences unless the user asks for more detail). "
    "You can answer factual questions, give opinions, help with problems, or "
    "just chat casually. Keep a bit of playful sass, but always give genuinely "
    "useful and accurate answers when asked for facts or help."
)


async def ask_gemini(history):
    """Send the conversation history to Gemini and return the reply text.
    Returns None on failure, or the string '__RATE_LIMITED__' if we hit
    Gemini's free-tier quota, so the caller can show a clearer message."""
    if not GEMINI_API_KEY:
        return None

    contents = [{"role": role, "parts": [{"text": text}]} for role, text in history]

    payload = {
        "contents": contents,
        "systemInstruction": {"parts": [{"text": CHAT_SYSTEM_PROMPT}]}
    }
    params = {"key": GEMINI_API_KEY}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GEMINI_API_URL, params=params, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    try:
                        return data['candidates'][0]['content']['parts'][0]['text']
                    except (KeyError, IndexError):
                        print(f"Unexpected Gemini response shape: {data}")
                        return None
                elif response.status == 429:
                    error_text = await response.text()
                    print(f"Gemini API rate limited (429): {error_text}")
                    return "__RATE_LIMITED__"
                else:
                    error_text = await response.text()
                    print(f"Gemini API returned status {response.status}: {error_text}")
                    return None
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return None


async def handle_chat_message(message):
    """Handle a message that's part of an ongoing chat with the bot."""
    if not GEMINI_API_KEY:
        await message.reply("❌ chat isn't set up yet — no GEMINI_API_KEY configured.", mention_author=False)
        return

    history = chat_histories.setdefault(message.author.id, [])
    history.append(("user", message.content))
    if len(history) > MAX_HISTORY_TURNS:
        del history[:-MAX_HISTORY_TURNS]

    async with message.channel.typing():
        reply_text = await ask_gemini(history)

    if reply_text == "__RATE_LIMITED__":
        await message.reply(
            "⏳ hit the free chat quota for now — give it a bit and try again.",
            mention_author=False
        )
    elif reply_text:
        history.append(("model", reply_text))
        if len(history) > MAX_HISTORY_TURNS:
            del history[:-MAX_HISTORY_TURNS]

        # Discord messages are capped at 2000 chars, split if needed
        chunks = [reply_text[i:i + 1900] for i in range(0, len(reply_text), 1900)] or [reply_text]
        for i, chunk in enumerate(chunks):
            await message.reply(chunk, mention_author=False)
    else:
        await message.reply("❌ couldn't get a response right now, try again in a bit.", mention_author=False)


# Commands that are safe to auto-trigger from a chat message (no required
# arguments beyond an optional @member), so calling them with no extra
# parsing can't blow up. Anything needing required args (poll, announce,
# afk reason, tictactoe opponent, cussout target) is left out on purpose —
# those still need the real ,command syntax.
SAFE_AUTO_COMMANDS = [
    'lexi', 'beyonce', 'rihanna', 'frankocean', 'future', 'manon',
    'serverinfo', 'help', 'avatar', 'banner', 'userinfo'
]


def detect_command_request(content):
    """If the chat message clearly names one of the safe commands (e.g.
    'use lexi', 'can you do the beyonce command'), return that command name."""
    content_lower = content.lower()
    for name in SAFE_AUTO_COMMANDS:
        if re.search(rf'\b{name}\b', content_lower):
            return name
    return None


async def try_run_requested_command(message):
    """If the message is asking to run one of SAFE_AUTO_COMMANDS, run it and
    return True. Otherwise return False so the caller falls back to chat."""
    requested = detect_command_request(message.content)
    if not requested:
        return False

    command_obj = bot.get_command(requested)
    if not command_obj:
        return False

    ctx = await bot.get_context(message)
    try:
        await command_obj.callback(ctx)
    except Exception as e:
        await message.reply(f"❌ Couldn't run `{requested}`: {e}", mention_author=False)
    return True

# ==================== GIF Provider Setup (Giphy primary, Klipy fallback) ====================
# Tenor's public API was deprecated by Google (cutoff June 30, 2026), so we no longer use it.

GIPHY_API_KEY = os.getenv('GIPHY_API_KEY')
KLIPY_API_KEY = os.getenv('KLIPY_API_KEY')

GIPHY_SEARCH_URL = "https://api.giphy.com/v1/gifs/search"
KLIPY_SEARCH_URL_TEMPLATE = "https://api.klipy.com/api/v1/{key}/gifs/search"


async def fetch_giphy_gifs(query, limit=25):
    """Fetch GIFs matching `query` from the Giphy API.
    Returns a list of (url, title) tuples so results can be filtered by name."""
    if not GIPHY_API_KEY:
        return []

    offset = random.randint(0, 50)
    params = {
        "api_key": GIPHY_API_KEY,
        "q": query,
        "limit": limit,
        "offset": offset,
        "rating": "g",
        "lang": "en"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(GIPHY_SEARCH_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    results = []
                    for result in data.get('data', []):
                        url = result.get('images', {}).get('original', {}).get('url')
                        if url:
                            title = result.get('title', '') or ''
                            results.append((url, title))
                    return results
                else:
                    print(f"Giphy API returned status {response.status}")
                    return []
    except Exception as e:
        print(f"Error fetching GIFs from Giphy: {e}")
        return []


def _extract_klipy_url_and_title(item):
    """Best-effort extraction of a usable GIF URL (and title) from a Klipy
    result item. Klipy's response shape nests quality tiers (hd/md/sm/xs)
    under a 'file' (sometimes 'files') key. This tries known shapes defensively."""
    title = item.get('title', '') or item.get('slug', '') or ''
    file_obj = item.get('file') or item.get('files') or {}

    if isinstance(file_obj, dict):
        for quality in ('md', 'hd', 'sm', 'xs'):
            tier = file_obj.get(quality)
            if isinstance(tier, dict):
                for fmt in ('gif', 'webp', 'mp4'):
                    fmt_data = tier.get(fmt)
                    if isinstance(fmt_data, dict) and fmt_data.get('url'):
                        return fmt_data['url'], title
                if tier.get('url'):
                    return tier['url'], title

    # Fallbacks in case the schema differs
    if item.get('url'):
        return item['url'], title
    if item.get('imageUrl'):
        return item['imageUrl'], title

    return None, title


async def fetch_klipy_gifs(query, limit=25):
    """Fetch GIFs matching `query` from the Klipy API.
    Returns a list of (url, title) tuples so results can be filtered by name."""
    if not KLIPY_API_KEY:
        return []

    url = KLIPY_SEARCH_URL_TEMPLATE.format(key=KLIPY_API_KEY)
    params = {
        "q": query,
        "customer_id": "discord-bot",
        "per_page": limit,
        "page": random.randint(1, 3)
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    items = data.get('data', {}).get('data', [])
                    results = []
                    for item in items:
                        gif_url, title = _extract_klipy_url_and_title(item)
                        if gif_url:
                            results.append((gif_url, title))
                    return results
                else:
                    print(f"Klipy API returned status {response.status}")
                    return []
    except Exception as e:
        print(f"Error fetching GIFs from Klipy: {e}")
        return []


async def fetch_gifs(search_queries, name_keywords=None):
    """Pick a random query from the given list and fetch GIFs from Giphy AND
    Klipy at the same time, merging both result pools together.

    If `name_keywords` is provided, results are filtered to only keep GIFs
    whose title actually contains one of those keywords (case-insensitive),
    so we get GIFs of the actual person/character rather than loosely
    related results. Falls back to the unfiltered pool if filtering finds
    nothing (so a command never comes back completely empty)."""
    query = random.choice(search_queries)

    giphy_results, klipy_results = await asyncio.gather(
        fetch_giphy_gifs(query),
        fetch_klipy_gifs(query)
    )

    combined = giphy_results + klipy_results

    if name_keywords:
        keywords_lower = [k.lower() for k in name_keywords]
        filtered = [
            url for url, title in combined
            if any(k in title.lower() for k in keywords_lower)
        ]
        if filtered:
            combined_urls = filtered
        else:
            combined_urls = [url for url, _ in combined]
    else:
        combined_urls = [url for url, _ in combined]

    # Remove duplicates while preserving order
    seen = set()
    unique_gifs = []
    for url in combined_urls:
        if url not in seen:
            seen.add(url)
            unique_gifs.append(url)

    return unique_gifs if unique_gifs else None


# Query lists per character/theme (used to be per-fetch-function, now shared)
HELLO_KITTY_QUERIES = [
    "hello kitty",
    "hello kitty and friends",
    "sanrio hello kitty",
    "hello kitty my melody",
    "hello kitty characters"
]

BEYONCE_QUERIES = [
    "beyonce",
    "beyonce dance",
    "beyonce performance",
    "beyonce queen",
    "beyonce slay"
]

RIHANNA_QUERIES = [
    "rihanna",
    "rihanna dance",
    "rihanna performance",
    "rihanna singer",
    "rihanna slay"
]

FRANKOCEAN_QUERIES = [
    "frank ocean singer"
]

FUTURE_QUERIES = [
    "future rapper",
    "future hendrix",
    "future pluto rapper",
    "future trap rapper",
    "future hip hop",
]

MANON_QUERIES = [
    "manon bannerman",
    "manon bannerman singer",
    "manon bannerman music",
]

# Track command processing with a SHORT delay
processing_lock = set()

@bot.event
async def on_ready():
    instance_id = os.getpid()
    print(f'{bot.user} is online! [PID: {instance_id}]')
    print(f'Bot ID: {bot.user.id}')
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} commands [PID: {instance_id}]')
    except Exception as e:
        print(f'Failed to sync commands: {e}')

@bot.event
async def on_message(message):
    """Custom message handler to prevent duplicate processing"""
    if message.author.bot:
        return
    
    # Check if the message author is AFK and clear their status
    if message.author.id in afk_users:
        afk_data = afk_users[message.author.id]
        
        try:
            if message.author.nick and message.author.nick.startswith('[AFK] '):
                original_nick = afk_data.get('original_nick')
                await message.author.edit(nick=original_nick)
        except:
            pass
        
        del afk_users[message.author.id]
        
        welcome_msg = await message.channel.send(f"{message.author.mention} BITCH IM BACK OUTTA MY COMA")
        await asyncio.sleep(10)
        try:
            await welcome_msg.delete()
        except:
            pass
    
    if bot.user in message.mentions and not message.reference:
        await message.reply("fuck u want")
        return

    for mentioned_user in message.mentions:
        if mentioned_user.id in afk_users:
            afk_data = afk_users[mentioned_user.id]
            display_name = mentioned_user.nick or mentioned_user.name
            await message.reply(
                f"💤 **{display_name}** is currently AFK: {afk_data['reason']}"
            )

    # If this message is a reply to one of the bot's own messages and isn't a
    # command, treat it as a continuation of a chat conversation.
    if message.reference and not message.content.startswith(','):
        ref_msg = message.reference.resolved
        if ref_msg is None:
            try:
                ref_msg = await message.channel.fetch_message(message.reference.message_id)
            except Exception:
                ref_msg = None

        if ref_msg and ref_msg.author.id == bot.user.id:
            handled = await try_run_requested_command(message)
            if not handled:
                await handle_chat_message(message)
            return

    if not message.content.startswith(','):
        return
    
    command_key = f"{message.id}"
    
    if command_key in processing_lock:
        print(f"[DUPLICATE BLOCKED] Message {message.id} is already being processed")
        return
    
    processing_lock.add(command_key)
    print(f"[PROCESSING] Message {message.id} - Lock acquired")
    
    try:
        await bot.process_commands(message)
    finally:
        await asyncio.sleep(3)
        processing_lock.discard(command_key)
        print(f"[RELEASED] Message {message.id} - Lock released")
        

@bot.after_invoke
async def after_any_command(ctx):
    """This runs after every command"""
    print(f"[AFTER_INVOKE] Command: {ctx.command.name} | User: {ctx.author} | Message ID: {ctx.message.id}")

# ==================== Fun Commands ====================

@bot.command(name='cussout')
async def cussout(ctx, member: discord.Member):
    """Cuss out a user - Only available to bot owner"""
    OWNER_ID = 1110957708506570804
    
    if ctx.author.id != OWNER_ID:
        await ctx.send(f"{ctx.author.mention} you aint my owner lil sport piss off cant use this shit")
        return
    
    cuss_message = "hey big bum motherfucker shut yo raggedy ass up u piece of shit"
    
    if ctx.message.reference:
        replied_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        await replied_message.reply(f"{member.mention} {cuss_message}")
    else:
        await ctx.send(f"{member.mention} {cuss_message}")

async def _send_gif_embed(ctx, gifs, color, fail_label):
    if gifs:
        random_gif = random.choice(gifs)

        embed = discord.Embed(color=color)
        embed.set_image(url=random_gif)
        embed.set_footer(
            text=f"Requested by {ctx.author.name}",
            icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
        )

        await ctx.reply(embed=embed, mention_author=False)
    else:
        await ctx.send(f"❌ Failed to fetch {fail_label} GIFs")

@bot.command(name='lexi', aliases=['Lexi', 'LEXI', 'lExi', 'lEXi', 'lEXI', 'LExi', 'LExI', 'LEXi'])
async def lexi(ctx):
    """Send a random Hello Kitty & Friends GIF"""
    try:
        gifs = await fetch_gifs(HELLO_KITTY_QUERIES, name_keywords=["hello kitty"])
        await _send_gif_embed(ctx, gifs, discord.Color.pink(), "Hello Kitty & Friends")
    except Exception as e:
        await ctx.send(f"❌ Failed to send Hello Kitty & Friends GIF: {e}")

@bot.command(name='beyonce', aliases=[
    'Beyonce', 'BEYONCE', 'BEyonce', 'BEYonce', 'BEYOnce', 'BEYONce', 'BEYONCe',
    'bEyonce', 'bEYonce', 'bEYOnce', 'bEYONce', 'bEYONCe', 'bEYONCE',
    'beYonce', 'beYOnce', 'beYONce', 'beYONCe', 'beYONCE',
    'beyOnce', 'beyONce', 'beyONCe', 'beyONCE',
    'beyoNce', 'beyoNCe', 'beyoNCE',
    'beyonCe', 'beyonCE',
    'beyoncE'
])
async def beyonce(ctx):
    """Send a random Beyonce GIF"""
    try:
        gifs = await fetch_gifs(BEYONCE_QUERIES, name_keywords=["beyonce", "beyoncé"])
        await _send_gif_embed(ctx, gifs, discord.Color.gold(), "Beyonce")
    except Exception as e:
        await ctx.send(f"❌ Failed to send Beyonce GIF: {e}")

@bot.command(name='rihanna', aliases=[
    'Rihanna', 'RIHANNA',
    'rIhanna', 'rIHanna', 'rIHAnna', 'rIHANna', 'rIHANNa', 'rIHANNA',
    'riHanna', 'riHAnna', 'riHANna', 'riHANNa', 'riHANNA',
    'rihAnna', 'rihANna', 'rihANNa', 'rihANNA',
    'rihaNna', 'rihaNNa', 'rihaNNA',
    'rihanNa', 'rihanNA',
    'rihannA',
    'RIhanna', 'RIHanna', 'RIHAnna', 'RIHANna', 'RIHANNa',
    'RiHanna', 'RiHAnna', 'RiHANna', 'RiHANNa', 'RiHANNA',
    'RihAnna', 'RihANna', 'RihANNa', 'RihANNA',
    'RihaNna', 'RihaNNa', 'RihaNNA',
    'RihanNa', 'RihanNA',
    'RihannA'
])
async def rihanna(ctx):
    """Send a random Rihanna GIF"""
    try:
        gifs = await fetch_gifs(RIHANNA_QUERIES, name_keywords=["rihanna"])
        await _send_gif_embed(ctx, gifs, discord.Color.gold(), "Rihanna")
    except Exception as e:
        await ctx.send(f"❌ Failed to send Rihanna GIF: {e}")

@bot.command(name='frankocean', aliases=[
    'frank ocean', 'Frank Ocean', 'FRANK OCEAN', 'Frank ocean', 'frank Ocean',
    'FRANK ocean', 'frank OCEAN', 'Frank OCEAN', 'FRANK Ocean',
    'Frankocean', 'FRANKOCEAN',
    'fRankocean', 'fRAnkocean', 'fRANkocean', 'fRANKocean', 'fRANKOcean', 'fRANKOCean', 'fRANKOCEan', 'fRANKOCEAn', 'fRANKOCEAN',
    'frAnkocean', 'frANkocean', 'frANKocean', 'frANKOcean', 'frANKOCean', 'frANKOCEan', 'frANKOCEAn', 'frANKOCEAN',
    'fraNkocean', 'fraNKocean', 'fraNKOcean', 'fraNKOCean', 'fraNKOCEan', 'fraNKOCEAn', 'fraNKOCEAN',
    'frankOcean', 'frankOCean', 'frankOCEan', 'frankOCEAn', 'frankOCEAN',
    'frankoCean', 'frankocEan', 'frankocEAn', 'frankocEAN',
    'frankoceAn', 'frankoceAN',
    'FrAnkocean', 'FrANkocean', 'FrANKocean', 'FrANKOcean', 'FrANKOCean', 'FrANKOCEan', 'FrANKOCEAn', 'FrANKOCEAN',
    'FraNkocean', 'FraNKocean', 'FraNKOcean', 'FraNKOCean', 'FraNKOCEan', 'FraNKOCEAn', 'FraNKOCEAN',
    'FrankOcean', 'FrankOCean', 'FrankOCEan', 'FrankOCEAn', 'FrankOCEAN',
    'FrankoCean', 'FrankocEan', 'FrankocEAn', 'FrankocEAN',
    'FrankoceAn', 'FrankoceAN',
    'FRANkocean', 'FRANKocean', 'FRANKOcean', 'FRANKOCean', 'FRANKOCEan', 'FRANKOCEAn', 'FRANKoCean',
])
async def frankocean(ctx):
    """Send a random Frank Ocean GIF"""
    try:
        gifs = await fetch_gifs(FRANKOCEAN_QUERIES, name_keywords=["frank ocean"])
        await _send_gif_embed(ctx, gifs, discord.Color.gold(), "Frank Ocean")
    except Exception as e:
        await ctx.send(f"❌ Failed to send Frank Ocean GIF: {e}")

@bot.command(name='future', aliases=[
    'Future', 'FUTURE',
    'fUture', 'fUTure', 'fUTUre', 'fUTURe', 'fUTURE',
    'fuTure', 'fuTUre', 'fuTURe', 'fuTURE',
    'futUre', 'futURe', 'futURE',
    'futuRe', 'futuRE',
    'futurE',
    'FUture', 'FUTure', 'FUTUre', 'FUTURe',
    'FuTure', 'FuTUre', 'FuTURe', 'FuTURE',
    'FutUre', 'FutURe', 'FutURE',
    'FutuRe',
    'FuturE',
    'FUTuRe', 'FUTuRE', 'FUTurE',
    'FUtuRe', 'FUtuRE', 'FUturE',
])
async def future(ctx):
    """Send a random Future the rapper GIF"""
    try:
        gifs = await fetch_gifs(FUTURE_QUERIES, name_keywords=["future"])
        await _send_gif_embed(ctx, gifs, discord.Color.gold(), "Future")
    except Exception as e:
        await ctx.send(f"❌ Failed to send Future GIF: {e}")

@bot.command(name='manon', aliases=[
    'Manon', 'MANON',
    'mAnon', 'mANon', 'mANOn', 'mANON',
    'maNon', 'maNOn', 'maNON',
    'manOn', 'manON',
    'manoN',
    'MAnon', 'MANon', 'MANOn',
    'MaNon', 'MaNOn', 'MaNON',
    'ManOn', 'ManON',
    'ManoN',
    'MAnOn', 'MAnON', 'MaNoN',
    'mANoN', 'mAnOn', 'mAnON', 'mAnoN',
])
async def manon(ctx):
    """Send a random Manon the singer GIF"""
    try:
        gifs = await fetch_gifs(MANON_QUERIES, name_keywords=["manon"])
        await _send_gif_embed(ctx, gifs, discord.Color.gold(), "Manon")
    except Exception as e:
        await ctx.send(f"❌ Failed to send Manon GIF: {e}")

# ==================== Utility Commands ====================

@bot.command(name='serverinfo')
async def serverinfo(ctx):
    """Display server information"""
    guild = ctx.guild
    embed = discord.Embed(
        title=guild.name,
        color=discord.Color.blue()
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    
    embed.add_field(name="Owner", value=guild.owner.mention, inline=True)
    embed.add_field(name="Members", value=guild.member_count, inline=True)
    embed.add_field(name="Roles", value=len(guild.roles), inline=True)
    embed.add_field(name="Created", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="Region", value=str(guild.preferred_locale), inline=True)
    embed.add_field(name="Boost Level", value=guild.premium_tier, inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='userinfo')
async def userinfo(ctx, member: discord.Member = None):
    """Display user information"""
    member = member or ctx.author
    embed = discord.Embed(
        title=f"{member.name}",
        color=member.color
    )
    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
    
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.add_field(name="Nickname", value=member.nick or "None", inline=True)
    embed.add_field(name="Status", value=str(member.status).title(), inline=True)
    embed.add_field(name="Joined", value=member.joined_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="Created", value=member.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="Roles", value=len(member.roles) - 1, inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='avatar')
async def avatar(ctx, member: discord.Member = None):
    """Display user's avatar"""
    member = member or ctx.author
    embed = discord.Embed(
        title=f"{member.name}'s Avatar",
        color=member.color
    )
    avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
    embed.set_image(url=avatar_url)
    embed.add_field(name="Download", value=f"[Click here]({avatar_url})")
    await ctx.send(embed=embed)

@bot.command(name='banner')
async def banner(ctx, member: discord.Member = None):
    """Display user's banner or server banner"""
    if member:
        user = await bot.fetch_user(member.id)
        if user.banner:
            embed = discord.Embed(
                title=f"{member.name}'s Banner",
                color=member.color
            )
            banner_url = user.banner.url
            embed.set_image(url=banner_url)
            embed.add_field(name="Download", value=f"[Click here]({banner_url})")
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"{member.mention} doesn't have a banner.")
    else:
        if ctx.guild.banner:
            embed = discord.Embed(
                title=f"{ctx.guild.name}'s Banner",
                color=discord.Color.blue()
            )
            banner_url = ctx.guild.banner.url
            embed.set_image(url=banner_url)
            embed.add_field(name="Download", value=f"[Click here]({banner_url})")
            await ctx.send(embed=embed)
        else:
            await ctx.send("This server doesn't have a banner.")

@bot.command(name='poll')
async def poll(ctx, question, *options):
    """Create a poll (,poll "Question" "Option 1" "Option 2")"""
    if len(options) > 10:
        await ctx.send("Maximum 10 options allowed.")
        return
    
    if len(options) < 2:
        await ctx.send("Please provide at least 2 options.")
        return
    
    embed = discord.Embed(
        title="📊 Poll",
        description=question,
        color=discord.Color.blue()
    )
    
    reactions = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
    
    for i, option in enumerate(options):
        embed.add_field(name=f"{reactions[i]} {option}", value="\u200b", inline=False)
    
    poll_msg = await ctx.send(embed=embed)
    
    for i in range(len(options)):
        await poll_msg.add_reaction(reactions[i])

@bot.command(name='announce')
@commands.has_permissions(manage_messages=True)
async def announce(ctx, channel: discord.TextChannel, *, message):
    """Send an announcement to a channel"""
    embed = discord.Embed(
        title="📢 Announcement",
        description=message,
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Announced by {ctx.author}")
    await channel.send(embed=embed)
    await ctx.send(f"Announcement sent to {channel.mention}")

@bot.command(name='forget')
async def forget(ctx):
    """Clear your chat history with the bot"""
    if ctx.author.id in chat_histories:
        del chat_histories[ctx.author.id]
        await ctx.reply("🧹 Alright, I forgot our conversation. Clean slate.")
    else:
        await ctx.reply("We haven't been chatting yet, nothing to forget.")

@bot.command(name='afk')
async def afk(ctx, *, reason="AFK"):
    """Set yourself as AFK with a custom message"""
    user_id = ctx.author.id
    
    original_nick = ctx.author.nick or ctx.author.name
    
    try:
        new_nick = f"[AFK] {original_nick}"
        if len(new_nick) <= 32:
            await ctx.author.edit(nick=new_nick)
    except:
        pass
    
    afk_users[user_id] = {
        'reason': reason,
        'original_nick': original_nick
    }
    
    embed = discord.Embed(
        title="you're now AFK 💤",
        description=f"see you later **{ctx.author.display_name}** 👋",
        color=0x9b59b6
    )
    embed.add_field(name="📝 Reason", value=f"> {reason}", inline=False)
    embed.set_footer(text="you'll be unmarked as AFK when you send a message")
    embed.set_thumbnail(url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
    await ctx.reply(embed=embed)

# ==================== Timezone Commands ====================

ALL_TIMEZONES = sorted(pytz.all_timezones)

@bot.tree.command(name="set_timezone", description="Set your timezone")
@app_commands.describe(timezone="Start typing your timezone (e.g. America/New_York)")
async def set_timezone(interaction: discord.Interaction, timezone: str):
    """Set your timezone via slash command with autocomplete"""
    if timezone not in pytz.all_timezones:
        await interaction.response.send_message(
            "❌ Invalid timezone. Please pick one from the autocomplete list.",
            ephemeral=True
        )
        return

    user_timezones[interaction.user.id] = timezone
    tz = pytz.timezone(timezone)
    now = datetime.now(tz)
    utc_offset = now.strftime('%z')
    utc_formatted = f"UTC{utc_offset[:3]}:{utc_offset[3:]}"

    embed = discord.Embed(
        title="🌍 Timezone Set!",
        description=f"your timezone has been saved, **{interaction.user.display_name}**",
        color=0x2ecc71
    )
    embed.add_field(name="🕐 Timezone", value=f"`{timezone}`", inline=True)
    embed.add_field(name="🔢 UTC Offset", value=f"`{utc_formatted}`", inline=True)
    embed.add_field(name="🕰️ Your Current Time", value=f"`{now.strftime('%A, %B %d %Y • %I:%M %p')}`", inline=False)
    embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else interaction.user.default_avatar.url)
    embed.set_footer(text="use ,timezone @user to check someone's time")
    await interaction.response.send_message(embed=embed)

@set_timezone.autocomplete('timezone')
async def timezone_autocomplete(interaction: discord.Interaction, current: str):
    """Autocomplete for timezone selection"""
    current_lower = current.lower()
    matches = [tz for tz in ALL_TIMEZONES if current_lower in tz.lower()][:25]
    return [app_commands.Choice(name=tz, value=tz) for tz in matches]

@bot.command(name='timezone')
async def timezone(ctx, arg: str = None, member: discord.Member = None):
    """Check your own or another user's current time, or remove your timezone"""

    # ,timezone remove
    if arg and arg.lower() == 'remove':
        if ctx.author.id in user_timezones:
            del user_timezones[ctx.author.id]
            await ctx.reply("✅ Your timezone has been removed.")
        else:
            await ctx.reply("❌ You don't have a timezone set.")
        return

    # ,timezone @user — arg will be None, member will be parsed separately
    # handle: ,timezone (no args = self), ,timezone @user
    if arg is not None and member is None:
        # arg might be a mention that didn't resolve, try converting
        try:
            target_id = int(arg.strip('<@!>'))
            target = ctx.guild.get_member(target_id) or ctx.author
        except:
            target = ctx.author
    elif member is not None:
        target = member
    else:
        target = ctx.author

    if target.id not in user_timezones:
        if target.id == ctx.author.id:
            await ctx.reply("❌ You haven't set a timezone yet. Use `/set_timezone` to set one.")
        else:
            await ctx.reply(f"❌ **{target.display_name}** hasn't set their timezone yet.")
        return

    tz_str = user_timezones[target.id]
    tz = pytz.timezone(tz_str)
    now = datetime.now(tz)
    utc_offset = now.strftime('%z')
    utc_formatted = f"UTC{utc_offset[:3]}:{utc_offset[3:]}"

    embed = discord.Embed(
        title=f"🕐 {target.display_name}'s Time",
        color=0x3498db
    )
    embed.add_field(name="🗓️ Date", value=f"`{now.strftime('%A, %B %d %Y')}`", inline=False)
    embed.add_field(name="🕰️ Time", value=f"`{now.strftime('%I:%M %p')}`", inline=True)
    embed.add_field(name="🌍 Timezone", value=f"`{tz_str}`", inline=True)
    embed.add_field(name="🔢 UTC Offset", value=f"`{utc_formatted}`", inline=True)
    embed.set_thumbnail(url=target.avatar.url if target.avatar else target.default_avatar.url)
    embed.set_footer(text="timezone set by the user via /set_timezone")
    await ctx.reply(embed=embed)

# ==================== Tic Tac Toe ====================

class TicTacToeButton(discord.ui.Button):
    def __init__(self, x: int, y: int):
        super().__init__(style=discord.ButtonStyle.secondary, label='\u200b', row=y)
        self.x = x
        self.y = y
    
    async def callback(self, interaction: discord.Interaction):
        view: TicTacToeView = self.view
        
        if interaction.user.id != view.current_player:
            await interaction.response.send_message("❌ It's not your turn!", ephemeral=True)
            return
        
        position = self.y * 3 + self.x
        if view.board[position] != ' ':
            await interaction.response.send_message("❌ That spot is already taken!", ephemeral=True)
            return
        
        symbol = 'X' if interaction.user.id == view.x_player else 'O'
        view.board[position] = symbol
        
        if symbol == 'X':
            self.style = discord.ButtonStyle.danger
            self.label = '❌'
        else:
            self.style = discord.ButtonStyle.primary
            self.label = '⭕'
        self.disabled = True
        
        winner = view.check_winner()
        
        if winner:
            for child in view.children:
                child.disabled = True
            
            if winner == 'tie':
                view.embed.title = "❌ Tic Tac Toe - Game Over! ⭕"
                view.embed.color = discord.Color.greyple()
                view.embed.clear_fields()
                view.embed.add_field(name="Result", value="🤝 It's a tie!")
            else:
                winner_user = view.x_user if winner == 'X' else view.o_user
                view.embed.title = "❌ Tic Tac Toe - Game Over! ⭕"
                view.embed.color = discord.Color.gold()
                view.embed.clear_fields()
                view.embed.add_field(name="Winner", value=f"🎉 {winner_user.mention} wins!")
            
            view.stop()
        else:
            view.current_player = view.o_player if view.current_player == view.x_player else view.x_player
            current_user = view.x_user if view.current_player == view.x_player else view.o_user
            current_symbol = '❌' if view.current_player == view.x_player else '⭕'
            
            view.embed.clear_fields()
            view.embed.add_field(name="Current Turn", value=f"{current_user.mention} ({current_symbol})")
        
        await interaction.response.edit_message(embed=view.embed, view=view)

class TicTacToeView(discord.ui.View):
    def __init__(self, x_user: discord.Member, o_user: discord.Member):
        super().__init__(timeout=300)
        self.x_user = x_user
        self.o_user = o_user
        self.x_player = x_user.id
        self.o_player = o_user.id
        self.current_player = self.x_player
        self.board = [' ' for _ in range(9)]
        
        self.embed = discord.Embed(
            title="❌ Tic Tac Toe ⭕",
            description=f"{x_user.mention} (❌) vs {o_user.mention} (⭕)",
            color=discord.Color.blue()
        )
        self.embed.add_field(name="Current Turn", value=f"{x_user.mention} (❌)")
        
        for y in range(3):
            for x in range(3):
                self.add_item(TicTacToeButton(x, y))
    
    def check_winner(self):
        winning_combos = [
            [0, 1, 2], [3, 4, 5], [6, 7, 8],
            [0, 3, 6], [1, 4, 7], [2, 5, 8],
            [0, 4, 8], [2, 4, 6]
        ]
        
        for combo in winning_combos:
            if self.board[combo[0]] == self.board[combo[1]] == self.board[combo[2]] != ' ':
                return self.board[combo[0]]
        
        if ' ' not in self.board:
            return 'tie'
        
        return None
    
    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        self.embed.add_field(name="Timeout", value="⏰ Game timed out!")
        try:
            await self.message.edit(embed=self.embed, view=self)
        except:
            pass

@bot.command(name='tictactoe')
async def tictactoe(ctx, opponent: discord.Member):
    """Start a tic tac toe game with another player"""
    if opponent.bot:
        await ctx.send("❌ You can't play against a bot!")
        return
    
    if opponent.id == ctx.author.id:
        await ctx.send("❌ You can't play against yourself!")
        return
    
    view = TicTacToeView(ctx.author, opponent)
    view.message = await ctx.send(embed=view.embed, view=view)

# ==================== Help Command ====================

@bot.command(name='help')
async def help_command(ctx):
    """Display help information"""
    embed = discord.Embed(
        title="🤖 Bot Commands",
        description="Prefix: `,`\nUse `,command` to run a command",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="🎉 Fun",
        value=(
            "`lexi` - Random Hello Kitty GIF\n"
            "`beyonce` - Random Beyonce GIF\n"
            "`rihanna` - Random Rihanna GIF\n"
            "`frankocean` - Random Frank Ocean GIF\n"
            "`future` - Random Future the Rapper GIF\n"
            "`manon` - Random Manon the Singer GIF\n"
            "`tictactoe @user` - Play tic-tac-toe\n"
            "`cussout @user` - Cuss out user (owner only)"
        ),
        inline=False
    )
    
    embed.add_field(
        name="💬 Chat",
        value=(
            "Ping me to say hi, then reply to my message to start chatting — "
            "ask me questions, facts, anything.\n"
            "`,forget` - Clear our chat history and start fresh"
        ),
        inline=False
    )

    embed.add_field(
        name="🔧 Utility",
        value=(
            "`serverinfo` - Server information\n"
            "`userinfo [@user]` - User information\n"
            "`avatar [@user]` - Show avatar\n"
            "`banner [@user]` - Show banner\n"
            "`poll \"question\" \"opt1\" \"opt2\"` - Create poll\n"
            "`announce #channel <message>` - Send announcement\n"
            "`afk [reason]` - Set AFK status\n"
            "`timezone [@user]` - Check your or someone's current time\n"
            "`timezone remove` - Remove your saved timezone\n"
            "`/set_timezone` - Set your timezone (with autocomplete)"
        ),
        inline=False
    )
    
    embed.set_footer(text="Made with 💖 | Use ,help to see this menu again")
    
    await ctx.send(embed=embed)

# ==================== Error Handling ====================

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing required argument: {error.param.name}")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Invalid argument provided.")
    else:
        await ctx.send(f"❌ An error occurred: {str(error)}")

# ==================== Run Bot ====================

TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    print("=" * 80)
    print("ERROR: No token found! Set DISCORD_TOKEN in .env file.")
    print(f"Current directory: {os.getcwd()}")
    print(f"Files in directory: {os.listdir('.')}")
    print("=" * 80)
    exit(1)

print(f"✓ Token loaded successfully (starts with: {TOKEN[:20]}...)")

if __name__ == "__main__":
    bot.run(TOKEN)
