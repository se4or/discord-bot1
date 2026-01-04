import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import datetime, timedelta
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot setup
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=',', intents=intents, help_command=None)

# Storage for warnings, mutes, and AFK users
warnings = {}
muted_users = {}
afk_users = {}
counting_channels = {}
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
    if message.author.bot:
        return
    
    if message.channel.id in counting_channels:
        game = counting_channels[message.channel.id]
        try:
            number = int(message.content.strip())
            if message.author.id == game['last_user']:
                await message.delete()
                fail_msg = await message.channel.send(f"{message.author.mention} at your big age still cant count smfh (can't count twice in a row, restarted to 1)")
                await asyncio.sleep(5)
                await fail_msg.delete()
                game['count'] = 0
                game['last_user'] = None
                return
            if number == game['count'] + 1:
                game['count'] = number
                game['last_user'] = message.author.id
                await message.add_reaction('✅')
            else:
                await message.delete()
                fail_msg = await message.channel.send(f"{message.author.mention} at your big age still cant count smfh (wrong number, count restarted to 1)")
                await asyncio.sleep(5)
                await fail_msg.delete()
                game['count'] = 0
                game['last_user'] = None
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
    print(f"[AFTER_INVOKE] Command: {ctx.command.name} | User: {ctx.author} | Message ID: {ctx.message.id}")

@bot.command(name='ban')
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    try:
        await member.ban(reason=reason)
        embed = discord.Embed(title="HA good riddance bitch", description=f"{member.mention} got the boot", color=discord.Color.red())
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Moderator", value=ctx.author.mention)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"Failed to ban member: {e}")

@bot.command(name='unban')
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int, *, reason="No reason provided"):
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user, reason=reason)
        await ctx.send(f"Unbanned {user.name}#{user.discriminator}")
    except Exception as e:
        await ctx.send(f"Failed to unban user: {e}")

@bot.command(name='kick')
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    try:
        await member.kick(reason=reason)
        embed = discord.Embed(title="Member Kicked", description=f"{member.mention} has been kicked", color=discord.Color.orange())
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Moderator", value=ctx.author.mention)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"Failed to kick member: {e}")

@bot.command(name='mute')
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member, duration: str = None, *, reason="No reason provided"):
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
        embed = discord.Embed(title="get muted ho", description=f"{member.mention} shut your mouth", color=discord.Color.blue())
        embed.add_field(name="Duration", value=duration or "28 days")
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Moderator", value=ctx.author.mention)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"Failed to mute member: {e}")

@bot.command(name='unmute')
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, member: discord.Member):
    try:
        await member.timeout(None)
        await ctx.send(f"{member.mention} has been unmuted.")
    except Exception as e:
        await ctx.send(f"Failed to unmute member: {e}")

@bot.command(name='warn')
@commands.has_permissions(manage_messages=True)
async def warn(ctx, member: discord.Member, *, reason="No reason provided"):
    guild_id = str(ctx.guild.id)
    user_id = str(member.id)
    if guild_id not in warnings:
        warnings[guild_id] = {}
    if user_id not in warnings[guild_id]:
        warnings[guild_id][user_id] = []
    warning = {'reason': reason, 'moderator': str(ctx.author), 'timestamp': datetime.now().isoformat()}
    warnings[guild_id][user_id].append(warning)
    warn_count = len(warnings[guild_id][user_id])
    embed = discord.Embed(title="the fucknigga has been warned", description=f"{member.mention} got their warning", color=discord.Color.yellow())
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
    guild_id = str(ctx.guild.id)
    user_id = str(member.id)
    if guild_id not in warnings or user_id not in warnings[guild_id]:
        await ctx.send(f"{member.mention} has no warnings.")
        return
    user_warnings = warnings[guild_id][user_id]
    embed = discord.Embed(title=f"Warnings for {member.name}", color=discord.Color.yellow())
    for i, warning in enumerate(user_warnings, 1):
        embed.add_field(name=f"Warning {i}", value=f"**Reason:** {warning['reason']}\n**Moderator:** {warning['moderator']}\n**Date:** {warning['timestamp'][:10]}", inline=False)
    await ctx.send(embed=embed)

@bot.command(name='clearwarns')
@commands.has_permissions(manage_messages=True)
async def clear_warnings(ctx, member: discord.Member):
    guild_id = str(ctx.guild.id)
    user_id = str(member.id)
    if guild_id in warnings and user_id in warnings[guild_id]:
        warnings[guild_id][user_id] = []
        await ctx.send(f"Cleared all warnings for {member.mention}")
    else:
        await ctx.send(f"{member.mention} has no warnings to clear.")

@bot.command(name='purge')
@commands.has_permissions(manage_messages=True)
async def purge(ctx, member: discord.Member = None, amount: int = None):
    if member is None and amount is None:
        await ctx.send("❌ Usage: `,purge @user amount` or `,purge amount`")
        return
    if amount is None and isinstance(member, int):
        amount = member
        member = None
    if amount is None:
        await ctx.send("❌ Please specify the amount of messages to delete.")
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
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send(f"🔒 {ctx.channel.mention} has been locked.")

@bot.command(name='unlock')
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send(f"🔓 {ctx.channel.mention} has been unlocked.")

@bot.command(name='slowmode')
@commands.has_permissions(manage_channels=True)
async def slowmode(ctx, seconds: int):
    await ctx.channel.edit(slowmode_delay=seconds)
    await ctx.send(f"Slowmode set to {seconds} seconds.")

@bot.command(name='addrole')
@commands.has_permissions(manage_roles=True)
async def addrole(ctx, member: discord.Member, *, role: discord.Role):
    try:
        await member.add_roles(role)
        embed = discord.Embed(title="here's your role mf", description=f"{member.mention} got {role.mention}", color=discord.Color.green())
        embed.add_field(name="Moderator", value=ctx.author.mention)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"Failed to add role: {e}")

@bot.command(name='removerole')
@commands.has_permissions(manage_roles=True)
async def removerole(ctx, member: discord.Member, *, role: discord.Role):
    try:
        await member.remove_roles(role)
        embed = discord.Embed(title="gimme that shit cry me a river", description=f"Took {role.mention} from {member.mention}", color=discord.Color.red())
        embed.add_field(name="Moderator", value=ctx.author.mention)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"Failed to remove role: {e}")

@bot.command(name='roleinfo')
async def roleinfo(ctx, *, role: discord.Role):
    embed = discord.Embed(title=f"Role Info: {role.name}", color=role.color)
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
    member = member or ctx.author
    roles = [role.mention for role in member.roles if role.name != "@everyone"]
    if not roles:
        await ctx.send(f"{member.mention} has no roles.")
        return
    embed = discord.Embed(title=f"Roles for {member.name}", description=", ".join(roles), color=member.color)
    embed.set_footer(text=f"Total roles: {len(roles)}")
    await ctx.send(embed=embed)

@bot.command(name='serverinfo')
async def serverinfo(ctx):
    guild = ctx.guild
    embed = discord.Embed(title=guild.name, color=discord.Color.blue())
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
    member = member or ctx.author
    embed = discord.Embed(title=f"{member.name}#{member.discriminator}", color=member.color)
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
    member = member or ctx.author
    embed = discord.Embed(title=f"{member.name}'s Avatar", color=member.color)
    avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
    embed.set_image(url=avatar_url)
    embed.add_field(name="Download", value=f"[Click here]({avatar_url})")
    await ctx.send(embed=embed)

@bot.command(name='banner')
async def banner(ctx, member: discord.Member = None):
    if member:
        user = await bot.fetch_user(member.id)
        if user.banner:
            embed = discord.Embed(title=f"{member.name}'s Banner", color=member.color)
            banner_url = user.banner.url
            embed.set_image(url=banner_url)
            embed.add_field(name="Download", value=f"[Click here]({banner_url})")
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"{member.mention} doesn't have a banner.")
    else:
        if ctx.guild.banner:
            embed = discord.Embed(title=f"{ctx.guild.name}'s Banner", color=discord.Color.blue())
            banner_url = ctx.guild.banner.url
            embed.set_image(url=banner_url)
            embed.add_field(name="Download", value=f"[Click here]({banner_url})")
            await ctx.send(embed=embed)
        else:
            await ctx.send("This server doesn't have a banner.")

@bot.command(name='poll')
async def poll(ctx, question, *options):
    if len(options) > 10:
        await ctx.send("Maximum 10 options allowed.")
        return
    if len(options) < 2:
        await ctx.send("Please provide at least 2 options.")
        return
    embed = discord.Embed(title="📊 Poll", description=question, color=discord.Color.blue())
    reactions = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
    for i, option in enumerate(options):
        embed.add_field(name=f"{reactions[i]} {option}", value="\u200b", inline=False)
    poll_msg = await ctx.send(embed=embed)
    for i in range(len(options)):
        await poll_msg.add_reaction(reactions[i])

@bot.command(name='announce')
@commands.has_permissions(manage_messages=True)
async def announce(ctx, channel: discord.TextChannel, *, message):
    embed = discord.Embed(title="📢 Announcement", description=message, color=discord.Color.gold())
    embed.set_footer(text=f"Announced by {ctx.author}")
    await channel.send(embed=embed)
    await ctx.send(f"Announcement sent to {channel.mention}")

@bot.command(name='afk')
async def afk(ctx, *, reason="AFK"):
    user_id = ctx.author.id
    original_nick = ctx.author.nick or ctx.author.name
    try:
        new_nick = f"[AFK] {original_nick}"
        if len(new_nick) <= 32:
            await ctx.author.edit(nick=new_nick)
    except:
        pass
    afk_users[user_id] = {'reason': reason, 'original_nick': original_nick}
    embed = discord.Embed(title="💤 AFK Status Set", description=f"{ctx.author.mention} is now AFK", color=discord.Color.greyple())
    embed.add_field(name="Reason", value=reason)
    await ctx.reply(embed=embed)

@bot.command(name='setcounting')
@commands.has_permissions(manage_channels=True)
async def setcounting(ctx):
    counting_channels[ctx.channel.id] = {'count': 0, 'last_user': None}
    embed = discord.Embed(title="🔢 Counting Game Started!", description=f"{ctx.channel.mention} is now a counting channel!", color=discord.Color.green())
    embed.add_field(name="Rules", value="• Start counting from 1\n• Each person can only count once in a row\n• Count sequentially (1, 2, 3...)\n• If you mess up, count resets to 1", inline=False)
    embed.add_field(name="Start", value="Someone type `1` to begin!", inline=False)
    await ctx.send(embed=embed)

@bot.command(name='removecounting')
@commands.has_permissions(manage_channels=True)
async def removecounting(ctx):
    if ctx.channel.id in counting_channels:
        del counting_channels[ctx.channel.id]
        await ctx.send("🔢 Counting game removed from this channel.")
    else:
        await ctx.send("❌ This channel is not a counting channel.")

@bot.command(name='countingstatus')
async def countingstatus(ctx):
    if ctx.channel.id in counting_channels:
        game = counting_channels[ctx.channel.id]
        embed = discord.Embed(title="🔢 Counting Status", description=f"Current count: **{game['count']}**", color=discord.Color.blue())
        if game['last_user']:
            last_user = await bot.fetch_user(game['last_user'])
            embed.add_field(name="Last Counter", value=last_user.mention)
        embed.add_field(name="Next Number", value=str(game['count'] + 1))
        await ctx.send(embed=embed)
    else:
        await ctx.send("❌ This channel is not a counting channel. Use `,setcounting` to start!")

@bot.command(name='resetcount')
@commands.has_permissions(manage_messages=True)
async def resetcount(ctx):
    if ctx.channel.id in counting_channels:
        counting_channels[ctx.channel.id]['count'] = 0
        counting_channels[ctx.channel.id]['last_user'] = None
        await ctx.send("🔢 Count has been reset to 0!")
    else:
        await ctx.send("❌ This channel is not a counting channel.")

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
        self.embed = discord.Embed(title="❌ Tic Tac Toe ⭕", description=f"{x_user.mention} (❌) vs {o_user.mention} (⭕)", color=discord.Color.blue())
        self.embed.add_field(name="Current Turn", value=f"{x_user.mention} (❌)")
        for y in range(3):
            for x in range(3):
                self.add_item(TicTacToeButton(x, y))
    
    def check_winner(self):
        winning_combos = [[0, 1, 2], [3, 4, 5], [6, 7, 8], [0, 3, 6], [1, 4, 7], [2, 5, 8], [0, 4, 8], [2, 4, 6]]
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
    if opponent.bot:
        await ctx.send("❌ You can't play against a bot!")
        return
    if opponent.id == ctx.author.id:
        await ctx.send("❌ You can't play against yourself!")
        return
    view = TicTacToeView(ctx.author, opponent)
    view.message = await ctx.send(embed=view.embed, view=view)

@bot.command(name='help')
async def help_command(ctx):
    embed = discord.Embed(title="Test1 Bot Commands", description="Prefix: `,`", color=discord.Color.blue())
    embed.add_field(name="🛡️ Moderation", value="`ban`, `unban`, `kick`, `mute`, `unmute`, `warn`, `warnings`, `clearwarns`, `purge`, `lock`, `unlock`, `slowmode`", inline=False)
    embed.add_field(name="👥 Role Management", value="`addrole`, `removerole`, `roleinfo`, `roles`", inline=False)
    embed.add_field(name="🔧 Utility", value="`serverinfo`, `userinfo`, `avatar`, `banner`, `poll`, `announce`, `afk`, `help`", inline=False)
    embed.add_field(name="🔢 Counting Game", value="`setcounting`, `removecounting`, `countingstatus`, `resetcount`", inline=False)
    embed.add_field(name="🎮 Games", value="`tictactoe` - Play tic tac toe with another user", inline=False)
    await ctx.send(embed=embed)

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

# ============================================================================
# BOT TOKEN - LOADED FROM ENVIRONMENT VARIABLES
# ============================================================================
TOKEN = os.getenv('DISCORD_TOKEN')

if not TOKEN:
    print("ERROR: No token found! Set DISCORD_TOKEN in .env file.")
    exit(1)

# Run the bot
if __name__ == "__main__":
    bot.run(TOKEN)
