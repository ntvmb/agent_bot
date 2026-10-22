import logging
import asyncio
import json
import datetime
import discord
from io import StringIO
from discord import (
    option,
    default_permissions,
    SlashCommandOptionType,
    guild_only,
    Option,
)
from discord.ext import tasks, commands
from . import server_vars
from . import global_vars
from .uptime import process_uptime_human_readable

bot = discord.Bot(intents=discord.Intents.all())
_log = logging.getLogger(__name__)


@bot.event
async def on_ready():
    watching = discord.Activity(
        type=discord.ActivityType.listening, name="the honeypots"
    )
    await bot.change_presence(activity=watching, status=discord.Status.dnd)
    _log.info(f"Logged in as {bot.user}.")
    global_vars.write("guild_count", len(bot.guilds))


@bot.event
async def on_application_command_error(
    ctx: discord.ApplicationContext, error: Exception
):
    if isinstance(error, commands.errors.MissingPermissions) or isinstance(
        error, commands.errors.NotOwner
    ):
        try:
            await ctx.respond(
                "I'm sorry, but I cannot let you do that.",
                ephemeral=True,
            )
        except Exception:
            _log.exception("Failed to send response.")
        _log.warning(
            f"{ctx.author} attempted to execute {ctx.command.name}, but does not have permission."
        )
    elif isinstance(error, commands.errors.NoPrivateMessage):
        try:
            await ctx.respond(
                "This command cannot be used in a DM context.", ephemeral=True
            )
        except Exception:
            _log.exception("Failed to send response.")
    else:
        _log.exception(
            f"An exception occurred while executing {ctx.command.name}.",
            exc_info=(type(error), error, error.__traceback__),
        )
        try:
            await ctx.respond(
                f"An exception occurred while executing this command:\n{error}",
                ephemeral=True,
            )
        except Exception:
            _log.exception("Failed to send response.")


@bot.event
async def on_message(message: discord.Message):
    # Only act on messages in servers
    if not isinstance(message.author, discord.Member):
        return
    # Don't respond to the bot's own messages
    if message.author.id == bot.user.id:
        return
    honeypot = server_vars.get("honeypot", message.guild.id)
    if (
        honeypot is not None
        and message.channel.id == honeypot
        and not message.author.bot
    ):
        try:
            await message.author.ban(
                delete_message_seconds=86400, reason="Fell for the honeypot"
            )
            _log.info(f"The honeypot in {message.guild} caught {message.author}!")
        except discord.errors.HTTPException:
            _log.exception(f"Failed to ban {message.author} from {message.guild}!")
            return


def _has_correct_permissions(
    ctx: discord.ApplicationContext, channel: discord.TextChannel
) -> bool:
    perms = channel.permissions_for(ctx.me)
    return perms.send_messages and perms.ban_members


@bot.slash_command(name="ping", description="Pong!")
async def ping(ctx: discord.ApplicationContext):
    from time import perf_counter_ns

    t1 = perf_counter_ns()
    await ctx.defer()
    t2 = perf_counter_ns()
    # How long did it take to defer the interaction?
    await ctx.respond(f"Pong! `{(t2 - t1)/1e6:.0f} ms`")


@bot.slash_command(name="uptime", description="Check Agent's uptime.")
async def uptime(ctx: discord.ApplicationContext):
    await ctx.respond(process_uptime_human_readable())


@bot.slash_command(name="set_honeypot", description="Set the honeypot channel.")
@default_permissions(manage_channels=True)
@guild_only()
async def set_honeypot(
    ctx: discord.ApplicationContext,
    channel: Option(discord.TextChannel, description="The channel to use."),  # type: ignore
):
    await ctx.defer(ephemeral=True)
    if _has_correct_permissions(ctx, channel):
        server_vars.write("honeypot", channel.id, ctx.guild_id)
        await ctx.respond(f"Okay, I will now monitor {channel.mention}.")
    else:
        await ctx.respond(
            "I cannot do as told because I do not have the correct permissions.\n"
            "Make sure I have the `Send Messages` and `Ban Members` permissions."
        )


@bot.slash_command(description="Get user info")
async def userinfo(
    ctx: discord.ApplicationContext,
    user: Option(discord.Member, description="User's mention or ID"),  # type: ignore
):
    await ctx.defer()
    user_in_guild = False
    user_joined_guild = None
    if not isinstance(user, (discord.User, discord.Member)):
        try:
            user = await bot.fetch_user(int(user))
        except discord.errors.NotFound:
            await ctx.respond("User does not exist.")
            return
        except TypeError:
            await ctx.respond("Not a valid ID.")
            return
    if ctx.guild is not None:
        member = ctx.guild.get_member(user.id)
        if member is not None:
            user = member
            if member.joined_at is not None:
                user_joined_guild = int(member.joined_at.timestamp())
                roles = member.roles
                user_in_guild = True
    embed = discord.Embed(
        title=str(user),
        thumbnail=user.display_avatar.url,
        description=f"{user.mention}"
    )
    embed = embed.add_field(
        name="Information",
        value=(
            f"**Bot**: {user.bot}\n"
            f"**ID**: `{user.id}`"
        )
    )
    user_joined_discord = int(user.created_at.timestamp())
    joined_field = StringIO()
    joined_field.write(f"**Discord**: <t:{user_joined_discord}:F> (<t:{user_joined_discord}:R>)\n")
    if user_in_guild:
        joined_field.write(f"**Guild**: <t:{user_joined_guild}:F> (<t:{user_joined_guild}:R>)")
    embed = embed.add_field(
        name="Joined",
        value=joined_field.getvalue(),
    )
    if user_in_guild:
        embed = embed.add_field(
            name="Guild-Specific",
            value=f"Roles: {', '.join(role.mention for role in roles)}",
            inline=False
        )
    await ctx.respond(embed=embed)


@bot.slash_command(description="Ban a member by mention or ID")
@default_permissions(ban_members=True)
@guild_only()
async def ban(
    ctx: discord.ApplicationContext,
    user: Option(discord.Member, description="User's mention or ID"),  # type: ignore
    reason: Option(str, description="Reason for ban", required=False),  # type: ignore
):
    await ctx.defer(ephemeral=True)
    ban_string = (
        f"Admin: {ctx.author}\n"
        f"Reason: {reason}\n"
        f"Timestamp: {datetime.datetime.now(datetime.timezone.utc).strftime("%a %Y/%m/%d, %T %Z")}"
    )
    if not isinstance(user, (discord.User, discord.Member)):
        user = await ctx.guild.fetch_member(int(user))
    try:
        await ctx.guild.ban(user, delete_message_seconds=86400, reason=ban_string)
    except discord.errors.Forbidden:
        await ctx.respond("I am unable to ban this user.")
        return
    await ctx.respond(f"Successfully banned {user}.")
