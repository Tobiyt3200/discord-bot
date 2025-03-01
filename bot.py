import os
import re  # REGEX DIGGA
import datetime
import discord
import aiohttp
import json
import requests  # website http requests (not used, but kept if needed)
from discord.ext import commands, tasks
from discord import app_commands
from sqlalchemy import create_engine, Column, String, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# 1. Load environment variables
load_dotenv()
MY_GUILD_ID = 1123917370583437364  # Replace with your server's ID
BOT_ENV = os.getenv("BOT_ENV", "test").lower()  # "test" or "production"
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or "mssql+pyodbc://localhost\\SQLEXPRESS/discord_bot_db?trusted_connection=yes"
)
MOD_CHANNEL_ID = os.getenv("MOD_CHANNEL_ID")
if MOD_CHANNEL_ID:
    MOD_CHANNEL_ID = int(MOD_CHANNEL_ID)
else:
    MOD_CHANNEL_ID = None

# 2. Set up SQLAlchemy
engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


# 3. Define the UserActivity table
class UserActivity(Base):
    __tablename__ = "user_activity"
    user_id = Column(String(255), primary_key=True)
    discord_name = Column(String(255))
    last_active = Column(DateTime, default=datetime.datetime.utcnow)


# 4. Create table if it doesn't exist
Base.metadata.create_all(engine)
print("Database connected and ensured 'user_activity' table exists.")


# 5. Helper function to update a user's activity
def update_user_activity(user_id, discord_name, timestamp):
    session = SessionLocal()
    try:
        record = session.query(UserActivity).filter_by(user_id=str(user_id)).first()
        if record:
            record.last_active = timestamp
            record.discord_name = discord_name
        else:
            record = UserActivity(
                user_id=str(user_id), discord_name=discord_name, last_active=timestamp
            )
            session.add(record)
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Error updating activity for user {user_id}: {e}")
    finally:
        session.close()


# 6. Define a Bot subclass that registers slash commands only in your guild
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True


class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Synchronize slash commands only for your guild
        try:
            print(f"Attempting to sync slash commands for guild {MY_GUILD_ID}...")
            guild = discord.Object(id=MY_GUILD_ID)
            await self.tree.sync(guild=guild)
            print("Slash commands synced for guild:", MY_GUILD_ID)
        except Exception as err:
            print(f"Error syncing commands: {err}")
bot = MyBot()

# 7. Standard events and prefix commands, restricted to your guild
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    check_inactivity.start()
    debug_task.start()


@bot.event
async def on_message(message):
    if message.guild is None or message.guild.id != MY_GUILD_ID:
        return
    if message.author.bot:
        return
    update_user_activity(message.author.id, message.author.name, message.created_at)
    await bot.process_commands(message)


@bot.event
async def on_voice_state_update(member, before, after):
    if after.channel is not None and member.guild.id == MY_GUILD_ID:
        update_user_activity(member.id, member.name, datetime.datetime.utcnow())


def is_in_guild(ctx):
    return ctx.guild and ctx.guild.id == MY_GUILD_ID

# Slash command version for ping
@bot.tree.command(name="ping", description="Replies with Pong!")
@app_commands.guilds(discord.Object(id=MY_GUILD_ID))
async def slash_ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong!")

# Slash command version for repeat
@bot.tree.command(name="repeat", description="Repeats the text you provide.")
@app_commands.describe(text="The text you want me to repeat.")
@app_commands.guilds(discord.Object(id=MY_GUILD_ID))
async def slash_repeat(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(text)

@bot.command(name="owner")
@commands.check(is_in_guild)
async def owner_command(ctx):
    await ctx.send("Tobi programmed me!")


# 8. Background Task: Check Inactivity
@tasks.loop(minutes=1)
async def check_inactivity():
    now = datetime.datetime.utcnow()
    threshold = (
        datetime.timedelta(weeks=3)
        if BOT_ENV == "production"
        else datetime.timedelta(minutes=1)
    )
    session = SessionLocal()
    try:
        records = session.query(UserActivity).all()
        for record in records:
            inactivity_duration = now - record.last_active
            print(
                f"[DEBUG] Checking user_id={record.user_id}, inactivity={inactivity_duration}, threshold={threshold}"
            )
            if inactivity_duration > threshold:
                for guild in bot.guilds:
                    if guild.id != MY_GUILD_ID:
                        continue
                    member = guild.get_member(int(record.user_id))
                    print(f"[DEBUG] Resolved to member={member}")
                    if member:
                        try:
                            if BOT_ENV == "production":
                                await member.send(
                                    "You have been inactive for over 3 weeks and will be removed from the server."
                                )
                            else:
                                await member.send(
                                    "TEST MODE: You would have been marked inactive."
                                )
                        except Exception as e:
                            print(f"Could not send DM to {member}: {e}")
                        try:
                            if BOT_ENV == "production":
                                await guild.kick(
                                    member, reason="Inactive for over 3 weeks"
                                )
                                print(f"Kicked {member} for inactivity.")
                                if MOD_CHANNEL_ID:
                                    mod_channel = bot.get_channel(MOD_CHANNEL_ID)
                                    if mod_channel:
                                        await mod_channel.send(
                                            f"Kicked {member.mention} for inactivity."
                                        )
                                    else:
                                        print("Mod channel not found.")
                            else:
                                print(
                                    f"[TEST MODE] {member} would have been kicked at {now}"
                                )
                        except Exception as e:
                            print(f"Failed to kick {member}: {e}")
    except Exception as e:
        print(f"Error in check_inactivity task: {e}")
    finally:
        session.close()


# 9. Background Task: Debug Count
@tasks.loop(minutes=15)
async def debug_task():
    session = SessionLocal()
    try:
        count = session.query(UserActivity).count()
    except Exception as e:
        count = "Error reading count"
        print(f"Error in debug_task: {e}")
    finally:
        session.close()
    debug_message = f"Debug: There are {count} user activity records as of {datetime.datetime.utcnow().isoformat()}."
    if MOD_CHANNEL_ID:
        channel = bot.get_channel(MOD_CHANNEL_ID)
        if channel:
            await channel.send(debug_message)
        else:
            print("Debug: Mod channel not found.")
    else:
        print(debug_message)


# 10. Deepwoken Build Logic

# Regex to validate link format
DEEPWOKEN_LINK_REGEX = re.compile(r"^https://deepwoken\.co/builder\?id=([A-Za-z0-9]+)$")

def extract_deepwoken_id(link: str) -> str | None:
    match = DEEPWOKEN_LINK_REGEX.match(link)
    if match:
        return match.group(1)
    return None

async def fetch_build_json(build_id: str) -> dict:
    """
    Fetches Deepwoken build data by parsing the HTML of the Next.js page.
    Raises an exception if the build data cannot be found.
    """
    url = f"https://deepwoken.co/builder?id={build_id}"

    # Use a desktop browser-like User-Agent to avoid minimal or blocked responses
    headers = {"User-Agent": "Mozilla/5.0"}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to fetch build. Status code: {resp.status}")
            html_text = await resp.text()

    # Try to find the Next.js JSON in a script tag with id="__NEXT_DATA__"
    match = re.search(
        r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        html_text,
        re.DOTALL
    )
    if not match:
        # Print out the first 500 chars of the page for debugging
        snippet = html_text[:500].replace("\n", "\\n")
        raise Exception(
            f"No Next.js JSON data found in page HTML.\nDebug snippet:\n{snippet}"
        )

    raw_json = match.group(1)

    # Parse the JSON object
    try:
        next_data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        raise Exception(f"Failed to parse Next.js data: {e}")

    # The build data is typically under props.pageProps.buildData
    build_data = next_data.get("props", {}).get("pageProps", {}).get("buildData")
    if not build_data:
        raise Exception("No 'buildData' object found in the Next.js data structure.")

    return build_data

def shrine_line(stat_name: str, pre_dict: dict, post_dict: dict) -> str:
    """
    Returns a string showing 'preVal (postVal)' if they differ, or just 'val' if they're the same.
    Example: '15 (20)' or '40'.
    """
    pre_val = pre_dict.get(stat_name, 0)
    post_val = post_dict.get(stat_name, 0)
    if pre_val == post_val:
        return str(pre_val)
    else:
        return f"{pre_val} ({post_val})"

def format_shrine_stats(build_data: dict) -> discord.Embed:
    """
    Creates a Discord embed comparing preShrine vs postShrine for base, attunement, and weapon.
    Also shows meta info (Race, Oath, Murmur, etc.).
    """
    stats_obj = build_data.get("stats", {})
    build_name = stats_obj.get("buildName", "Unknown Build")
    build_desc = stats_obj.get("buildDescription", "")
    meta_obj = stats_obj.get("meta", {})

    embed = discord.Embed(
        title=build_name,
        description=build_desc,
        color=0x00FF00,
        timestamp=datetime.datetime.utcnow(),
    )
    embed.set_footer(text="Deepwoken Build")

    author = build_data.get("author", {})
    author_name = author.get("name", "Unknown Author")
    embed.set_author(name=author_name)

    # Meta information
    race = meta_obj.get("Race", "None")
    oath = meta_obj.get("Oath", "None")
    murmur = meta_obj.get("Murmur", "None")
    origin = meta_obj.get("Origin", "None")
    bell = meta_obj.get("Bell", "None")
    outfit = meta_obj.get("Outfit", "None")

    meta_str = (
        f"**Race:** {race}\n"
        f"**Oath:** {oath}\n"
        f"**Murmur:** {murmur}\n"
        f"**Origin:** {origin}\n"
        f"**Bell:** {bell}\n"
        f"**Outfit:** {outfit}\n"
    )
    embed.add_field(name="Meta", value=meta_str, inline=False)

    # Pre- and Post-shrine stats
    pre_shrine = build_data.get("preShrine", {})
    post_shrine = build_data.get("postShrine", {})

    pre_base = pre_shrine.get("base", {})
    pre_attunement = pre_shrine.get("attunement", {})
    pre_weapon = pre_shrine.get("weapon", {})

    post_base = post_shrine.get("base", {})
    post_attunement = post_shrine.get("attunement", {})
    post_weapon = post_shrine.get("weapon", {})

    # Base stats embed field
    base_stat_keys = [
        "Strength", "Fortitude", "Agility", 
        "Intelligence", "Willpower", "Charisma"
    ]
    base_stats_lines = [
        f"**{stat}:** {shrine_line(stat, pre_base, post_base)}"
        for stat in base_stat_keys
    ]
    embed.add_field(name="Base Stats (Pre -> Post)", value="\n".join(base_stats_lines), inline=False)

    # Attunement embed field
    attune_keys = [
        "Flamecharm", "Frostdraw", "Thundercall",
        "Galebreathe", "Shadowcast", "Ironsing", "Bloodrend"
    ]
    attunement_stats_lines = [
        f"**{stat}:** {shrine_line(stat, pre_attunement, post_attunement)}"
        for stat in attune_keys
    ]
    embed.add_field(name="Attunements", value="\n".join(attunement_stats_lines), inline=False)

    # Weapon stats embed field
    weapon_keys = ["Heavy Wep.", "Medium Wep.", "Light Wep."]
    weapon_stats_lines = [
        f"**{stat}:** {shrine_line(stat, pre_weapon, post_weapon)}"
        for stat in weapon_keys
    ]
    embed.add_field(name="Weapon Stats", value="\n".join(weapon_stats_lines), inline=False)

    return embed

@bot.tree.command(name="build", description="Submit a Deepwoken build link")
@app_commands.describe(
    link="The Deepwoken builder link (e.g. https://deepwoken.co/builder?id=HylA35nm)"
)
@app_commands.guilds(discord.Object(id=MY_GUILD_ID))
async def build_command(interaction: discord.Interaction, link: str):
    build_id = extract_deepwoken_id(link)
    if not build_id:
        await interaction.response.send_message(
            "Invalid link! Must be like https://deepwoken.co/builder?id=XXXXXXXX",
            ephemeral=True,
        )
        return

    # Send an initial response to let the user know the build is being processed
    await interaction.response.send_message("Fetching build data...", ephemeral=True)

    try:
        build_data = await fetch_build_json(build_id)
    except Exception as e:
        await interaction.followup.send(
            f"Error fetching build data: {e}", ephemeral=True
        )
        return

    embed = format_shrine_stats(build_data)
    await interaction.followup.send(embed=embed)

@bot.tree.command(
    name="kickwithrole",
    description="Kicks members with a selected role."
)
@app_commands.describe(
    role="Select a role to kick members with that role."
)
@app_commands.guilds(discord.Object(id=MY_GUILD_ID))
async def kick_with_role(interaction: discord.Interaction, role: discord.Role):
    # Check if the invoking user has the mod role
    mod_role = discord.utils.get(interaction.guild.roles, name="mod")
    if not mod_role:
        await interaction.response.send_message("Mod role not found in this server.", ephemeral=True)
        return
    if mod_role not in interaction.user.roles:
        await interaction.response.send_message("You must have the mod role to use this command.", ephemeral=True)
        return

    # Gather members who have the provided role
    to_kick = [member for member in interaction.guild.members if role in member.roles]
    if not to_kick:
        await interaction.response.send_message("No members found with the role.", ephemeral=True)
        return

    kicked_count = 0
    errors = []
    for member in to_kick:
        try:
            await member.kick(reason="Kicked via /kickwithrole command")
            kicked_count += 1
        except Exception as e:
            errors.append(f"Failed to kick {member}: {e}")
            print(f"Error kicking {member}: {e}")

    response_message = f"Kicked {kicked_count} members with the role {role.name}."
    if errors:
        response_message += " Some errors occurred:\n" + "\n".join(errors)
    await interaction.response.send_message(response_message, ephemeral=True)


@bot.tree.command(
    name="kicknoroles",
    description="Kicks members with no additional roles (only the default @everyone)."
)
@app_commands.guilds(discord.Object(id=MY_GUILD_ID))
async def kick_no_roles(interaction: discord.Interaction):
    # Check if the invoking user has the mod role
    mod_role = discord.utils.get(interaction.guild.roles, name="mod")
    if not mod_role:
        await interaction.response.send_message("Mod role not found in this server.", ephemeral=True)
        return
    if mod_role not in interaction.user.roles:
        await interaction.response.send_message("You must have the mod role to use this command.", ephemeral=True)
        return

    # Gather members who have no roles other than @everyone
    to_kick = [member for member in interaction.guild.members if len(member.roles) <= 1]
    if not to_kick:
        await interaction.response.send_message("No members found with no additional roles.", ephemeral=True)
        return

    kicked_count = 0
    errors = []
    for member in to_kick:
        try:
            await member.kick(reason="Kicked via /kicknoroles command")
            kicked_count += 1
        except Exception as e:
            errors.append(f"Failed to kick {member}: {e}")
            print(f"Error kicking {member}: {e}")

    response_message = f"Kicked {kicked_count} members with no additional roles."
    if errors:
        response_message += " Some errors occurred:\n" + "\n".join(errors)
    await interaction.response.send_message(response_message, ephemeral=True)


bot.run(DISCORD_TOKEN)
