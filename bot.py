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

# Storage for warnings, mutes, and AFK users (in production, use a database)
warnings = {}
muted_users = {}
afk_users = {}  # {user_id: {'reason': 'reason', 'original_nick': 'nick'}}

# Counting game storage with persistent file
COUNTING_DATA_FILE = 'counting_data.json'

# Tenor API configuration
TENOR_API_KEY = "AIzaSyAyimkuYQYF_FXVALexPuGQctUWRURdCYQ"  # Public Tenor API key
TENOR_SEARCH_URL = "https://tenor.googleapis.com/v2/search"

async def fetch_hello_kitty_gifs():
    """Fetch random Hello Kitty GIFs from Tenor API"""
    # Use a random position to get different results each time
    random_pos = random.randint(0, 100)
    
    params = {
        "q": "hello kitty",
        "key": TENOR_API_KEY,
        "client_key": "discord_bot",
        "limit": 50,
        "pos": str(random_pos)  # This helps randomize which batch of results you get
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(TENOR_SEARCH_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    # Get the GIF URL from each result
                    gifs = [result['media_formats']['gif']['url'] for result in data.get('results', [])]
                    return gifs if gifs else None
                else:
                    print(f"Tenor API returned status {response.status}")
                    return None
    except Exception as e:
        print(f"Error fetching GIFs from Tenor: {e}")
        return None

def load_counting_data():
    """Load counting data from file"""
    try:
        if os.path.exists(COUNTING_DATA_FILE):
            with open(COUNTING_DATA_FILE, 'r') as f:
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
    except Exception as e:
        print(f"Error loading counting data: {e}")
    return {}

def save_counting_data():
    """Save counting data to file"""
    try:
        with open(COUNTING_DATA_FILE, 'w') as f:
            json.dump(counting_channels, f, indent=4)
    except Exception as e:
        print(f"Error saving counting data: {e}")

# Load counting channels from file on startup
counting_channels = load_counting_data()

# Track command processing with a SHORT delay
processing_lock = set()

@bot.event
async def on_ready():
    instance_id = os.getpid()
    print(f'{bot.user} is online! [PID: {instance_id}]')
    print(f'Bot ID: {bot.user.id}')
    print(f'Loaded {len(counting_channels)} counting channels from storage')
    if counting_channels:
        print(f'Counting channel IDs: {list(counting_channels.keys())}')
        for channel_id, data in counting_channels.items():
            print(f'  Channel {channel_id}: count={data.get("count")}, highest={data.get("highest_count")}')
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
    
    # Check if bot is mentioned (but not in a reply to avoid double responses)
    if bot.user in message.mentions and not message.reference:
        await message.reply("fuck u want")
    
    # Check for AFK users in mentions
    for mentioned_user in message.mentions:
        if mentioned_user.id in afk_users:
            afk_data = afk_users[mentioned_user.id]
            await message.reply(
                f"💤 {mentioned_user.mention} is currently AFK: {afk_data['reason']}",
                delete_after=5
            )
    
    # Check if this is a counting channel
    if message.channel.id in counting_channels:
        game = counting_channels[message.channel.id]
        
        try:
            number = int(message.content.strip())
            
            if game['count'] == 0 and number != 1:
                await message.delete()
                fail_msg = await message.channel.send(f"{message.author.mention} bruh we at 0, start from 1 dumbass")
                await asyncio.sleep(5)
                await fail_msg.delete()
                return
            
            if message.author.id == game['last_user']:
                await message.delete()
                fail_msg = await message.channel.send(f"{message.author.mention} calm down Einstein you know how to count we get it cant count twice in a row bro")
                await asyncio.sleep(5)
                await fail_msg.delete()
                game['count'] = 0
                game['last_user'] = None
                game['fails'] = game.get('fails', 0) + 1
                save_counting_data()
                return
            
            if number == game['count'] + 1:
                game['count'] = number
                game['last_user'] = message.author.id
                game['total_counts'] = game.get('total_counts', 0) + 1
                
                if number > game.get('highest_count', 0):
                    game['highest_count'] = number
                
                save_counting_data()
                await message.add_reaction('✅')
                
                if number in [10, 50, 100, 500, 1000, 5000, 10000]:
                    milestone_msg = await message.channel.send(f"🎉 **MILESTONE REACHED!** The count is now at **{number}**! 🎉")
                    await asyncio.sleep(10)
                    try:
                        await milestone_msg.delete()
                    except:
                        pass
            else:
                await message.delete()
                expected = game['count'] + 1
                fail_msg = await message.channel.send(f"{message.author.mention} at your big age still cant count smfh (expected {expected}, got {number}. Count restarted to 1)")
                await asyncio.sleep(5)
                await fail_msg.delete()
                game['count'] = 0
                game['last_user'] = None
                game['fails'] = game.get('fails', 0) + 1
                save_counting_data()
        except ValueError:
            pass
    
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

@bot.before_invoke
async def before_any_command(ctx):
    """This runs before every command"""
    print(f"[BEFORE_INVOKE] Command: {ctx.command.name} | User: {ctx.author} | Message ID: {ctx.message.id}")
    
    if ctx.author.id in afk_users:
        afk_data = afk_users[ctx.author.id]
        try:
            if ctx.author.nick and ctx.author.nick.startswith('[AFK] '):
                original_nick = afk_data.get('original_nick')
                await ctx.author.edit(nick=original_nick)
        except:
            pass
        
        del afk_users[ctx.author.id]
        welcome_msg = await ctx.send(f"{ctx.author.mention} BITCH IM BACK OUTTA MY COMA")
        await asyncio.sleep(5)
        try:
            await welcome_msg.delete()
        except:
            pass

@bot.after_invoke
async def after_any_command(ctx):
    """This runs after every command"""
    print(f"[AFTER_INVOKE] Command: {ctx.command.name} | User: {ctx.author} | Message ID: {ctx.message.id}")

# ==================== Moderation Commands ====================

@bot.command(name='ban')
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    """Ban a member from the server"""
    try:
        await member.ban(reason=reason)
        embed = discord.Embed(
            title="HA good riddance bitch",
            description=f"{member.mention} got the boot",
            color=discord.Color.red()
        )
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Moderator", value=ctx.author.mention)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"Failed to ban member: {e}")

@bot.command(name='unban')
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int, *, reason="No reason provided"):
    """Unban a user by ID"""
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user, reason=reason)
        await ctx.send(f"Unbanned {user.name}")
    except Exception as e:
        await ctx.send(f"Failed to unban user: {e}")

@bot.command(name='kick')
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    """Kick a member from the server"""
    try:
        await member.kick(reason=reason)
        embed = discord.Embed(
            title="Member Kicked",
            description=f"{member.mention} has been kicked",
            color=discord.Color.orange()
        )
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Moderator", value=ctx.author.mention)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"Failed to kick member: {e}")

@bot.command(name='mute')
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member, duration: str = None, *, reason="No reason provided"):
    """Mute a member (e.g., ,mute @user 10m reason)"""
    try:
        time_dict = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
        if duration:
            time_value = int(duration[:-1])
            time_unit = duration[-1]
            seconds = time_value * time_dict.get(time_unit, 60)
            until = discord.utils.utcnow() + timedelta(seconds=seconds)
        else:
            until = discord.utils.utcnow() + timedelta(days=28)
        
        await member.timeout(until, reason=reason)
        
        embed = discord.Embed(
            title="get muted ho",
            description=f"{member.mention} shut your mouth",
            color=discord.Color.blue()
        )
        embed.add_field(name="Duration", value=duration or "28 days")
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Moderator", value=ctx.author.mention)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"Failed to mute member: {e}")

@bot.command(name='unmute')
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, member: discord.Member):
    """Unmute a member"""
    try:
        await member.timeout(None)
        await ctx.send(f"{member.mention} has been unmuted.")
    except Exception as e:
        await ctx.send(f"Failed to unmute member: {e}")

@bot.command(name='warn')
@commands.has_permissions(manage_messages=True)
async def warn(ctx, member: discord.Member, *, reason="No reason provided"):
    """Warn a member"""
    guild_id = str(ctx.guild.id)
    user_id = str(member.id)
    
    if guild_id not in warnings:
        warnings[guild_id] = {}
    if user_id not in warnings[guild_id]:
        warnings[guild_id][user_id] = []
    
    warning = {
        'reason': reason,
        'moderator': str(ctx.author),
        'timestamp': datetime.now().isoformat()
    }
    warnings[guild_id][user_id].append(warning)
    
    warn_count = len(warnings[guild_id][user_id])
    
    embed = discord.Embed(
        title="the fucknigga has been warned",
        description=f"{member.mention} got their warning",
        color=discord.Color.yellow()
    )
    embed.add_field(name="Reason", value=reason)
    embed.add_field(name="Total Warnings", value=str(warn_count))
    embed.add_field(name="Moderator", value=ctx.author.mention)
    await ctx.send(embed=embed)
    
    try:
        await member.send(f"You have been warned in {ctx.guild.name} for: {reason}")
    except:
        pass

@bot.command(name='warnings')
@commands.has_permissions(manage_messages=True)
async def view_warnings(ctx, member: discord.Member):
    """View warnings for a member"""
    guild_id = str(ctx.guild.id)
    user_id = str(member.id)
    
    if guild_id not in warnings or user_id not in warnings[guild_id]:
        await ctx.send(f"{member.mention} has no warnings.")
        return
    
    user_warnings = warnings[guild_id][user_id]
    embed = discord.Embed(
        title=f"Warnings for {member.name}",
        color=discord.Color.yellow()
    )
    
    for i, warning in enumerate(user_warnings, 1):
        embed.add_field(
            name=f"Warning {i}",
            value=f"**Reason:** {warning['reason']}\n**Moderator:** {warning['moderator']}\n**Date:** {warning['timestamp'][:10]}",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='clearwarns')
@commands.has_permissions(manage_messages=True)
async def clear_warnings(ctx, member: discord.Member):
    """Clear all warnings for a member"""
    guild_id = str(ctx.guild.id)
    user_id = str(member.id)
    
    if guild_id in warnings and user_id in warnings[guild_id]:
        warnings[guild_id][user_id] = []
        await ctx.send(f"Cleared all warnings for {member.mention}")
    else:
        await ctx.send(f"{member.mention} has no warnings to clear.")

@bot.command(name='purge')
@commands.has_permissions(manage_messages=True)
async def purge(ctx, amount: int = None, member: discord.Member = None):
    """Delete messages - usage: ,purge <amount> or ,purge <amount> @user"""
    if amount is None:
        await ctx.send("❌ Usage: `,purge <amount>` or `,purge <amount> @user`")
        return
    
    if amount > 100:
        await ctx.send("Cannot delete more than 100 messages at once.")
        return
    
    if amount < 1:
        await ctx.send("Amount must be at least 1.")
        return
    
    try:
        if member:
            def check(m):
                return m.author.id == member.id
            
            deleted = await ctx.channel.purge(limit=100, check=check)
            deleted = deleted[:amount]
            msg = await ctx.send(f"Deleted {len(deleted)} messages from {member.mention}.")
        else:
            deleted = await ctx.channel.purge(limit=amount + 1)
            msg = await ctx.send(f"Deleted {len(deleted) - 1} messages.")
        
        await asyncio.sleep(3)
        await msg.delete()
    except Exception as e:
        await ctx.send(f"Failed to purge messages: {e}")

@bot.command(name='lock')
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    """Lock the current channel"""
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send(f"🔒 {ctx.channel.mention} has been locked.")

@bot.command(name='unlock')
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    """Unlock the current channel"""
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send(f"🔓 {ctx.channel.mention} has been unlocked.")

@bot.command(name='slowmode')
@commands.has_permissions(manage_channels=True)
async def slowmode(ctx, seconds: int):
    """Set slowmode for the channel"""
    await ctx.channel.edit(slowmode_delay=seconds)
    await ctx.send(f"Slowmode set to {seconds} seconds.")

# ==================== Role Management ====================

@bot.command(name='addrole')
@commands.has_permissions(manage_roles=True)
async def addrole(ctx, member: discord.Member, *, role: discord.Role):
    """Give a role to a member"""
    try:
        await member.add_roles(role)
        embed = discord.Embed(
            title="here's your role mf",
            description=f"{member.mention} got {role.mention}",
            color=discord.Color.green()
        )
        embed.add_field(name="Moderator", value=ctx.author.mention)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"Failed to add role: {e}")

@bot.command(name='removerole')
@commands.has_permissions(manage_roles=True)
async def removerole(ctx, member: discord.Member, *, role: discord.Role):
    """Remove a role from a member"""
    try:
        await member.remove_roles(role)
        embed = discord.Embed(
            title="gimme that shit cry me a river",
            description=f"Took {role.mention} from {member.mention}",
            color=discord.Color.red()
        )
        embed.add_field(name="Moderator", value=ctx.author.mention)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"Failed to remove role: {e}")

@bot.command(name='roleinfo')
async def roleinfo(ctx, *, role: discord.Role):
    """Display information about a role"""
    embed = discord.Embed(
        title=f"Role Info: {role.name}",
        color=role.color
    )
    embed.add_field(name="ID", value=role.id, inline=True)
    embed.add_field(name="Color", value=str(role.color), inline=True)
    embed.add_field(name="Members", value=len(role.members), inline=True)
    embed.add_field(name="Mentionable", value="Yes" if role.mentionable else "No", inline=True)
    embed.add_field(name="Hoisted", value="Yes" if role.hoist else "No", inline=True)
    embed.add_field(name="Position", value=role.position, inline=True)
    embed.add_field(name="Created", value=role.created_at.strftime("%Y-%m-%d"), inline=True)
    await ctx.send(embed=embed)

@bot.command(name='roles')
async def roles(ctx, member: discord.Member = None):
    """List all roles of a member"""
    member = member or ctx.author
    roles = [role.mention for role in member.roles if role.name != "@everyone"]
    
    if not roles:
        await ctx.send(f"{member.mention} has no roles.")
        return
    
    embed = discord.Embed(
        title=f"Roles for {member.name}",
        description=", ".join(roles),
        color=member.color
    )
    embed.set_footer(text=f"Total roles: {len(roles)}")
    await ctx.send(embed=embed)

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
    """Send a random Hello Kitty GIF from Tenor"""
    try:
        # Fetch fresh GIFs from Tenor API
        gifs = await fetch_hello_kitty_gifs()
        
        if gifs:
            random_gif = random.choice(gifs)
            await ctx.reply(f"{ctx.author.mention} {random_gif}")
        else:
            await ctx.send(f"❌ Failed to fetch Hello Kitty GIFs from Tenor")
    except Exception as e:
        await ctx.send(f"❌ Failed to send Hello Kitty GIF: {e}")

def hex_to_color(hex_code):
    """Convert hex code to discord.Color"""
    hex_code = hex_code.strip('#')
    return discord.Color(int(hex_code, 16))

@bot.command(name='rolecolor')
async def rolecolor(ctx):
    """Create a custom colored role with your username"""
    await ctx.send(f"{ctx.author.mention} Please provide a hex color code (e.g., #FF5733 or FF5733):")
    
    def check(m):
        return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id
    
    try:
        hex_msg = await bot.wait_for('message', check=check, timeout=60.0)
        hex_code = hex_msg.content.strip()
        
        try:
            color = hex_to_color(hex_code)
        except ValueError:
            await ctx.send("❌ Invalid hex code! Please use format like #FF5733 or FF5733")
            return
        
        user_roles = [role for role in ctx.author.roles if role.name != "@everyone"]
        highest_role = max(user_roles, key=lambda r: r.position) if user_roles else None
        
        role_name = ctx.author.name
        new_role = await ctx.guild.create_role(
            name=role_name,
            color=color,
            reason=f"Custom color role for {ctx.author}"
        )
        
        if highest_role:
            try:
                await new_role.edit(position=highest_role.position + 1)
            except discord.Forbidden:
                await ctx.send("⚠️ Role created but couldn't move it above your highest role. Bot role might be too low.")
        
        await ctx.author.add_roles(new_role)
        
        embed = discord.Embed(
            title="✨ Custom Role Created!",
            description=f"Role **{role_name}** has been created with your custom color!",
            color=color
        )
        embed.add_field(name="Hex Code", value=hex_code.upper())
        embed.set_footer(text=f"Created for {ctx.author}")
        await ctx.send(embed=embed)
        
    except asyncio.TimeoutError:
        await ctx.send("❌ Timeout! You took too long to respond.")

@bot.command(name='gradientrole')
async def gradientrole(ctx):
    """Create a gradient colored role"""
    await ctx.send(f"{ctx.author.mention} Please provide the FIRST hex color code (e.g., #FF5733):")
    
    def check(m):
        return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id
    
    try:
        hex_msg1 = await bot.wait_for('message', check=check, timeout=60.0)
        hex_code1 = hex_msg1.content.strip()
        
        try:
            color1 = hex_to_color(hex_code1)
        except ValueError:
            await ctx.send("❌ Invalid hex code! Please use format like #FF5733 or FF5733")
            return
        
        await ctx.send(f"{ctx.author.mention} Now provide the SECOND hex color code:")
        
        hex_msg2 = await bot.wait_for('message', check=check, timeout=60.0)
        hex_code2 = hex_msg2.content.strip()
        
        try:
            color2 = hex_to_color(hex_code2)
        except ValueError:
            await ctx.send("❌ Invalid hex code! Please use format like #FF5733 or FF5733")
            return
        
        r1, g1, b1 = color1.r, color1.g, color1.b
        r2, g2, b2 = color2.r, color2.g, color2.b
        
        mid_r = (r1 + r2) // 2
        mid_g = (g1 + g2) // 2
        mid_b = (b1 + b2) // 2
        
        gradient_color = discord.Color.from_rgb(mid_r, mid_g, mid_b)
        
        user_roles = [role for role in ctx.author.roles if role.name != "@everyone"]
        highest_role = max(user_roles, key=lambda r: r.position) if user_roles else None
        
        role_name = ctx.author.name
        new_role = await ctx.guild.create_role(
            name=role_name,
            color=gradient_color,
            reason=f"Gradient color role for {ctx.author}"
        )
        
        if highest_role:
            try:
                await new_role.edit(position=highest_role.position + 1)
            except discord.Forbidden:
                await ctx.send("⚠️ Role created but couldn't move it above your highest role. Bot role might be too low.")
        
        await ctx.author.add_roles(new_role)
        
        embed = discord.Embed(
            title="🌈 Gradient Role Created!",
            description=f"Role **{role_name}** has been created with a gradient color!",
            color=gradient_color
        )
        embed.add_field(name="Color 1", value=hex_code1.upper(), inline=True)
        embed.add_field(name="Color 2", value=hex_code2.upper(), inline=True)
        embed.add_field(name="Result", value=f"#{mid_r:02x}{mid_g:02x}{mid_b:02x}".upper(), inline=True)
        embed.set_footer(text=f"Created for {ctx.author} | Note: Discord shows the middle gradient color")
        await ctx.send(embed=embed)
        
    except asyncio.TimeoutError:
        await ctx.send("❌ Timeout! You took too long to respond.")

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
        title="💤 AFK Status Set",
        description=f"{ctx.author.mention} is now AFK",
        color=discord.Color.greyple()
    )
    embed.add_field(name="Reason", value=reason)
    await ctx.reply(embed=embed)

# ==================== Counting Game ====================

@bot.command(name='setcounting')
@commands.has_permissions(manage_channels=True)
async def setcounting(ctx):
    """Set the current channel as a counting channel"""
    if ctx.channel.id in counting_channels:
        await ctx.send("❌ This channel is already a counting channel! Use `,countingstatus` to see the current count.")
        return
    
    counting_channels[ctx.channel.id] = {
        'count': 0,
        'last_user': None,
        'total_counts': 0,
        'highest_count': 0,
        'fails': 0
    }
    save_counting_data()
    
    embed = discord.Embed(
        title="🔢 Counting Game Started!",
        description=f"{ctx.channel.mention} is now a counting channel!",
        color=discord.Color.green()
    )
    embed.add_field(name="Rules", value="• Start counting from 1\n• Each person can only count once in a row\n• Count sequentially (1, 2, 3...)\n• If you mess up, count resets to 1\n• After a reset, the next number MUST be 1", inline=False)
    embed.add_field(name="Start", value="Someone type `1` to begin!", inline=False)
    embed.set_footer(text="📊 Stats are being tracked! Use ,countingstatus to view")
    await ctx.send(embed=embed)

@bot.command(name='removecounting')
@commands.has_permissions(manage_channels=True)
async def removecounting(ctx):
    """Remove counting game from the current channel"""
    if ctx.channel.id in counting_channels:
        game = counting_channels[ctx.channel.id]
        embed = discord.Embed(
            title="🔢 Counting Game Removed",
            description="Final Statistics",
            color=discord.Color.red()
        )
        embed.add_field(name="Highest Count Reached", value=str(game.get('highest_count', 0)), inline=True)
        embed.add_field(name="Total Numbers Counted", value=str(game.get('total_counts', 0)), inline=True)
        embed.add_field(name="Total Fails", value=str(game.get('fails', 0)), inline=True)
        
        del counting_channels[ctx.channel.id]
        save_counting_data()
        await ctx.send(embed=embed)
    else:
        await ctx.send("❌ This channel is not a counting channel.")

@bot.command(name='countingstatus')
async def countingstatus(ctx):
    """Check the current count in this channel"""
    if ctx.channel.id in counting_channels:
        game = counting_channels[ctx.channel.id]
        embed = discord.Embed(
            title="🔢 Counting Status",
            description=f"Current count: **{game['count']}**",
            color=discord.Color.blue()
        )
        if game['last_user']:
            try:
                last_user = await bot.fetch_user(game['last_user'])
                embed.add_field(name="Last Counter", value=last_user.mention, inline=True)
            except:
                embed.add_field(name="Last Counter", value="Unknown User", inline=True)
        
        embed.add_field(name="Next Number", value=str(game['count'] + 1), inline=True)
        embed.add_field(name="Highest Count", value=str(game.get('highest_count', 0)), inline=True)
        embed.add_field(name="Total Counts", value=str(game.get('total_counts', 0)), inline=True)
        embed.add_field(name="Total Fails", value=str(game.get('fails', 0)), inline=True)
        
        total = game.get('total_counts', 0) + game.get('fails', 0)
        if total > 0:
            success_rate = (game.get('total_counts', 0) / total) * 100
            embed.add_field(name="Success Rate", value=f"{success_rate:.1f}%", inline=True)
        
        await ctx.send(embed=embed)
    else:
        await ctx.send("❌ This channel is not a counting channel. Use `,setcounting` to start!")

@bot.command(name='resetcount')
@commands.has_permissions(manage_messages=True)
async def resetcount(ctx):
    """Reset the count in this channel"""
    if ctx.channel.id in counting_channels:
        old_count = counting_channels[ctx.channel.id]['count']
        counting_channels[ctx.channel.id]['count'] = 0
        counting_channels[ctx.channel.id]['last_user'] = None
        save_counting_data()
        
        embed = discord.Embed(
            title="🔢 Count Manually Reset",
            description=f"Count has been reset from {old_count} to 0!",
            color=discord.Color.orange()
        )
        embed.add_field(name="Next Number", value="1")
        embed.set_footer(text=f"Reset by {ctx.author}")
        await ctx.send(embed=embed)
    else:
        await ctx.send("❌ This channel is not a counting channel.")

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
        """Check if there's a winner"""
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
        title="Test1 Bot Commands",
        description="Prefix: ,",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="🎉 Fun",
        value="`lexi` - Send a random Hello Kitty GIF",
        inline=False
    )
    
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
