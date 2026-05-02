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
 
# Tenor API configuration
TENOR_API_KEY = "AIzaSyAyimkuYQYF_FXVALexPuGQctUWRURdCYQ"  # Public Tenor API key
TENOR_SEARCH_URL = "https://tenor.googleapis.com/v2/search"
 
async def fetch_hello_kitty_gifs():
    """Fetch random Hello Kitty and Friends GIFs from Tenor API"""
    random_pos = random.randint(0, 100)
    
    search_queries = [
        "hello kitty",
        "hello kitty and friends",
        "sanrio hello kitty",
        "hello kitty my melody",
        "hello kitty characters"
    ]
    
    search_query = random.choice(search_queries)
    
    params = {
        "q": search_query,
        "key": TENOR_API_KEY,
        "client_key": "discord_bot",
        "limit": 50,
        "pos": str(random_pos)
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(TENOR_SEARCH_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    gifs = [result['media_formats']['gif']['url'] for result in data.get('results', [])]
                    return gifs if gifs else None
                else:
                    print(f"Tenor API returned status {response.status}")
                    return None
    except Exception as e:
        print(f"Error fetching GIFs from Tenor: {e}")
        return None
 
async def fetch_beyonce_gifs():
    """Fetch random Beyonce GIFs from Tenor API"""
    random_pos = random.randint(0, 100)
    
    search_queries = [
        "beyonce",
        "beyonce dance",
        "beyonce performance",
        "beyonce queen",
        "beyonce slay"
    ]
    
    search_query = random.choice(search_queries)
    
    params = {
        "q": search_query,
        "key": TENOR_API_KEY,
        "client_key": "discord_bot",
        "limit": 50,
        "pos": str(random_pos)
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(TENOR_SEARCH_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    gifs = [result['media_formats']['gif']['url'] for result in data.get('results', [])]
                    return gifs if gifs else None
                else:
                    print(f"Tenor API returned status {response.status}")
                    return None
    except Exception as e:
        print(f"Error fetching GIFs from Tenor: {e}")
        return None
 
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
    
    for mentioned_user in message.mentions:
        if mentioned_user.id in afk_users:
            afk_data = afk_users[mentioned_user.id]
            display_name = mentioned_user.nick or mentioned_user.name
            await message.reply(
                f"💤 **{display_name}** is currently AFK: {afk_data['reason']}"
            )
    
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
 
@bot.command(name='lexi', aliases=['Lexi', 'LEXI', 'lExi', 'lEXi', 'lEXI', 'LExi', 'LExI', 'LEXi'])
async def lexi(ctx):
    """Send a random Hello Kitty & Friends GIF from Tenor"""
    try:
        gifs = await fetch_hello_kitty_gifs()
        
        if gifs:
            random_gif = random.choice(gifs)
            
            embed = discord.Embed(
                color=discord.Color.pink()
            )
            embed.set_image(url=random_gif)
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
            
            await ctx.reply(embed=embed, mention_author=False)
        else:
            await ctx.send(f"❌ Failed to fetch Hello Kitty & Friends GIFs from Tenor")
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
    """Send a random Beyonce GIF from Tenor"""
    try:
        gifs = await fetch_beyonce_gifs()
        
        if gifs:
            random_gif = random.choice(gifs)
            
            embed = discord.Embed(
                color=discord.Color.gold()
            )
            embed.set_image(url=random_gif)
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
            
            await ctx.reply(embed=embed, mention_author=False)
        else:
            await ctx.send(f"❌ Failed to fetch Beyonce GIFs from Tenor")
    except Exception as e:
        await ctx.send(f"❌ Failed to send Beyonce GIF: {e}")
 
async def fetch_rihanna_gifs():
    """Fetch random Rihanna GIFs from Tenor API"""
    random_pos = random.randint(0, 100)
    
    search_queries = [
        "rihanna",
        "rihanna dance",
        "rihanna performance",
        "rihanna singer",
        "rihanna slay"
    ]
    
    search_query = random.choice(search_queries)
    
    params = {
        "q": search_query,
        "key": TENOR_API_KEY,
        "client_key": "discord_bot",
        "limit": 50,
        "pos": str(random_pos)
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(TENOR_SEARCH_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    gifs = [result['media_formats']['gif']['url'] for result in data.get('results', [])]
                    return gifs if gifs else None
                else:
                    print(f"Tenor API returned status {response.status}")
                    return None
    except Exception as e:
        print(f"Error fetching GIFs from Tenor: {e}")
        return None
 
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
    """Send a random Rihanna GIF from Tenor"""
    try:
        gifs = await fetch_rihanna_gifs()
        
        if gifs:
            random_gif = random.choice(gifs)
            
            embed = discord.Embed(
                color=discord.Color.gold()
            )
            embed.set_image(url=random_gif)
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
            
            await ctx.reply(embed=embed, mention_author=False)
        else:
            await ctx.send(f"❌ Failed to fetch Rihanna GIFs from Tenor")
    except Exception as e:
        await ctx.send(f"❌ Failed to send Rihanna GIF: {e}")
 
async def fetch_frankocean_gifs():
    """Fetch random Frank Ocean GIFs from Tenor API"""
    random_pos = random.randint(0, 100)
    
    params = {
        "q": "frank ocean singer",
        "key": TENOR_API_KEY,
        "client_key": "discord_bot",
        "limit": 50,
        "pos": str(random_pos)
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(TENOR_SEARCH_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    gifs = []
                    for result in data.get('results', []):
                        title = result.get('title', '').lower()
                        tags = [tag.lower() for tag in result.get('tags', [])]
                        if 'frank ocean' in title or 'frank ocean' in ' '.join(tags):
                            gifs.append(result['media_formats']['gif']['url'])
                    # fallback if filter returns nothing
                    if not gifs:
                        gifs = [result['media_formats']['gif']['url'] for result in data.get('results', [])]
                    return gifs if gifs else None
                else:
                    print(f"Tenor API returned status {response.status}")
                    return None
    except Exception as e:
        print(f"Error fetching GIFs from Tenor: {e}")
        return None
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(TENOR_SEARCH_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    gifs = [result['media_formats']['gif']['url'] for result in data.get('results', [])]
                    return gifs if gifs else None
                else:
                    print(f"Tenor API returned status {response.status}")
                    return None
    except Exception as e:
        print(f"Error fetching GIFs from Tenor: {e}")
        return None
 
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
    """Send a random Frank Ocean GIF from Tenor"""
    try:
        gifs = await fetch_frankocean_gifs()
        
        if gifs:
            random_gif = random.choice(gifs)
            
            embed = discord.Embed(
                color=discord.Color.gold()
            )
            embed.set_image(url=random_gif)
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
            
            await ctx.reply(embed=embed, mention_author=False)
        else:
            await ctx.send(f"❌ Failed to fetch Frank Ocean GIFs from Tenor")
    except Exception as e:
        await ctx.send(f"❌ Failed to send Frank Ocean GIF: {e}")
 
async def fetch_future_gifs():
    """Fetch random Future the rapper GIFs from Tenor API"""
    random_pos = random.randint(0, 100)
 
    search_queries = [
        "future rapper",
        "future hendrix",
        "future pluto rapper",
        "future trap rapper",
        "future hip hop",
    ]
 
    search_query = random.choice(search_queries)
 
    params = {
        "q": search_query,
        "key": TENOR_API_KEY,
        "client_key": "discord_bot",
        "limit": 50,
        "pos": str(random_pos)
    }
 
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(TENOR_SEARCH_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    gifs = [result['media_formats']['gif']['url'] for result in data.get('results', [])]
                    return gifs if gifs else None
                else:
                    print(f"Tenor API returned status {response.status}")
                    return None
    except Exception as e:
        print(f"Error fetching GIFs from Tenor: {e}")
        return None
 
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
    """Send a random Future the rapper GIF from Tenor"""
    try:
        gifs = await fetch_future_gifs()
 
        if gifs:
            random_gif = random.choice(gifs)
 
            embed = discord.Embed(
                color=discord.Color.gold()
            )
            embed.set_image(url=random_gif)
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
 
            await ctx.reply(embed=embed, mention_author=False)
        else:
            await ctx.send(f"❌ Failed to fetch Future GIFs from Tenor")
    except Exception as e:
        await ctx.send(f"❌ Failed to send Future GIF: {e}")
 
async def fetch_manon_gifs():
    """Fetch random Manon Bannerman GIFs from Tenor API"""
    random_pos = random.randint(0, 100)
 
    search_queries = [
        "manon bannerman",
        "manon bannerman singer",
        "manon bannerman music",
        "manon bannerman performance",
        "manon bannerman swiss singer",
    ]
 
    search_query = random.choice(search_queries)
 
    params = {
        "q": search_query,
        "key": TENOR_API_KEY,
        "client_key": "discord_bot",
        "limit": 50,
        "pos": str(random_pos)
    }
 
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(TENOR_SEARCH_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    gifs = [result['media_formats']['gif']['url'] for result in data.get('results', [])]
                    return gifs if gifs else None
                else:
                    print(f"Tenor API returned status {response.status}")
                    return None
    except Exception as e:
        print(f"Error fetching GIFs from Tenor: {e}")
        return None
 
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
    """Send a random Manon the singer GIF from Tenor"""
    try:
        gifs = await fetch_manon_gifs()
 
        if gifs:
            random_gif = random.choice(gifs)
 
            embed = discord.Embed(
                color=discord.Color.gold()
            )
            embed.set_image(url=random_gif)
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
 
            await ctx.reply(embed=embed, mention_author=False)
        else:
            await ctx.send(f"❌ Failed to fetch Manon GIFs from Tenor")
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
 
