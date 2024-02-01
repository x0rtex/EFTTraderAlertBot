import asyncio
from datetime import datetime, timedelta
import requests
import os
import discord
from discord import option
from discord.ext import commands
from dotenv import load_dotenv

bot = commands.Bot(help_command=commands.DefaultHelpCommand())


@bot.event
async def on_ready() -> None:
    await bot.change_presence(activity=discord.Game("/help"))
    print(f"Logged in as {bot.user}")
    print(f"Guilds: {len(bot.guilds)}")


def make_graphql_request(query: str) -> dict:
    headers = {"Content-Type": "application/json"}
    response = requests.post('https://api.tarkov.dev/graphql', headers=headers, json={'query': query})
    response.raise_for_status()
    return response.json()


def run_query() -> dict:
    query = """
    {
        traderResetTimes() {
            name,
            resetTimestamp
        }
    }
    """
    return make_graphql_request(query)


# Parse graphql response into simple dictionary
def parse_data(data: dict) -> dict[str, str]:
    return {entry['name']: entry['resetTimestamp'] for entry in data['data']['traderResetTimes']
            if entry['name'] not in {'fence', 'lightkeeper', 'btr driver'}}


# Get timedelta between current time and next trader restock
def get_time_left(trader_reset_times: dict, selected_trader: str) -> timedelta:
    timestamp: str = trader_reset_times[selected_trader.lower()]
    timestamp_datetime = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S.%fZ')
    time_left: timedelta = timestamp_datetime - datetime.now()
    return time_left


# /remind
@bot.slash_command(name="remind", description="Get reminded before a trader restocks.")
@option(name="trader", description="Choose which trader reset you want a reminder for.",
        choices=["Prapor", "Therapist", "Fence", "Skier", "Peacekeeper", "Mechanic", "Ragman", "Jaeger"])
@option(name="minutes_before", description="How many minutes early you want to be reminded.")
@commands.cooldown(1, 5, commands.BucketType.user)
async def remind(ctx: discord.ApplicationContext, trader: str, mins_before: int) -> None:
    reset_times: dict[str, str] = parse_data(run_query())
    time_left: timedelta = get_time_left(reset_times, trader)

    if time_left.total_seconds() <= 0:
        await ctx.respond("Cannot set a reminder for a trader that has already reset.")
        return

    mins_before: int = min(mins_before, int(time_left.total_seconds() // 60))
    reminder_timer: int = max(0, time_left.total_seconds() - (mins_before * 60))

    await ctx.respond(f"**{trader.capitalize()}** will reset in **{(time_left.total_seconds() / 60):.1f} minute(s)**. "
                      f"You will be reminded **{mins_before} minute(s)** before they reset.")

    await asyncio.sleep(reminder_timer)
    reminder_msg = await ctx.send(f"<@{ctx.user.id}> **{trader.capitalize()}** will reset in **{mins_before} minute(s)**.")

    await asyncio.sleep(mins_before * 60)
    await reminder_msg.edit(content=f"<@{ctx.user.id}> **{trader.capitalize()}** has reset!")


# /traders
@bot.slash_command(name="traders", description="View trader restock timers")
@commands.cooldown(1, 5, commands.BucketType.user)
async def traders(ctx: discord.ApplicationContext) -> None:
    reset_times: dict[str, str] = parse_data(run_query())
    embed_msg = discord.Embed(title="Trader Reset Timers")

    for trader, timestamp in reset_times.items():
        time_left: timedelta = get_time_left(reset_times, trader)

        hours, remainder = divmod(time_left.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if time_left.total_seconds() < 0:
            mins_ago: int = int(abs(time_left.total_seconds()) // 60)
            embed_msg.add_field(name=trader.capitalize(), value=f"Reset {mins_ago}m ago")
        else:
            embed_msg.add_field(name=trader.capitalize(), value=f"{hours}h {minutes}m {seconds}s")

    await ctx.respond(embed=embed_msg)


# Application command error handler
@bot.event
async def on_application_command_error(ctx: discord.ApplicationContext, error: discord.DiscordException) -> None:
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.respond(
            f":hourglass: **This command is currently on cooldown.** Try again in {round(error.retry_after, 1)}s.",
            ephemeral=True)
    else:
        raise error


def run_bot() -> None:
    if os.name != "nt":
        import uvloop
        uvloop.install()
    load_dotenv()
    bot.run(os.getenv("TOKEN"))


if __name__ == "__main__":
    run_bot()
