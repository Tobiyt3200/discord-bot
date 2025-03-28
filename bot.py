import os
import re  # REGEX DIGGA
import discord
import aiohttp
import json
import threading
from difflib import get_close_matches
import requests  # website http requests
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv
from flask import Flask
from threading import Thread
import datetime

# app = Flask('')

# @app.route('/')
# def home():
#     return "Bot is alive!"

# def run():
#     app.run(host='0.0.0.0', port=8080)

# def keep_alive():
#     t = Thread(target=run)
#     t.start()

# 1. Load environment variables
load_dotenv()
MY_GUILD_ID = 1123917370583437364
BOT_ENV = os.getenv("BOT_ENV", "test").lower()  # "test" or "production"
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SERVER_ICON_URL = os.getenv("SERVER_ICON_URL")
MOD_CHANNEL_ID = os.getenv("MOD_CHANNEL_ID")
if MOD_CHANNEL_ID:
    MOD_CHANNEL_ID = int(MOD_CHANNEL_ID)
else:
    MOD_CHANNEL_ID = None

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

class MyBot(commands.Bot):
    # def __init__(self):
    #     super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        try:
            print(f"Attempting to sync slash commands for guild {MY_GUILD_ID}...")
            # await bot.tree.sync(guild=discord.Object(id=MY_GUILD_ID))
            # await self.tree.sync(guild=discord.Object(id=MY_GUILD_ID))
            # await bot.tree.sync()
            # await self.tree.sync()
            print("Slash commands synced for guild:", MY_GUILD_ID)
        except Exception as err:
            print(f"Error syncing commands: {err}")


bot = MyBot(command_prefix="!", intents=intents)


# -----------------
#   foundation
# -----------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    channel = bot.get_channel(MOD_CHANNEL_ID)
    if channel:
        today = datetime.datetime.now().strftime("%d.%m.%Y")
        message = f"Debug session started: {bot.user.name} on {today}"
        await channel.send(message)
    else:
        print("Channel not found!")
    print(f" ------- Discord Bot is Ready to go! -------")


def is_in_guild(ctx):
    return ctx.guild and ctx.guild.id == MY_GUILD_ID

@bot.tree.command(name="ping", description="Replies with Pong!")
@app_commands.guilds(discord.Object(id=MY_GUILD_ID))
async def slash_ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong!")

@bot.tree.command(name="repeat", description="Repeats the text you provide.")#
@app_commands.guilds(discord.Object(id=MY_GUILD_ID))
async def slash_repeat(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(text)

@bot.tree.command(name="owner")
@app_commands.guilds(discord.Object(id=MY_GUILD_ID))
async def owner_command(interaction: discord.Interaction):
    await ctx.send("Tobi programmed me!")

# ---------------------------------------------------------------------------
# Global Data & Helper Functions
# ---------------------------------------------------------------------------
def load_json(filename: str) -> dict:
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return {}

def load_categories(talents: dict) -> dict:
    categories = {}
    for category in talents.get("categories", []):
        name = category.get("name", "Unknown Category")
        categories[name.lower()] = category
    return categories

# Load global data (if file exists)
TALENTS_DATA = load_json("talents.json")
CATEGORIES_DATA = load_categories(TALENTS_DATA)
BOSSES_LIST = ["Duke Erisia", "Overlord Azur", "Warden Korr"]

async def fetch_wiki_data(
    title: str, prop: str = "extracts", extra_params: dict = None
) -> dict:
    base_url = "https://deepwoken.fandom.com/api.php"
    params = {
        "action": "query",
        "titles": title,
        "format": "json",
        "prop": prop,
    }
    if prop == "extracts":
        params.update({"exintro": "", "explaintext": ""})
    if extra_params:
        params.update(extra_params)
    async with aiohttp.ClientSession() as session:
        async with session.get(base_url, params=params) as response:
            if response.status != 200:
                raise Exception(f"API responded with status code {response.status}")
            data = await response.json()
            return data


def parse_wiki_response(data: dict) -> dict:
    try:
        pages = data["query"]["pages"]
        page = next(iter(pages.values()))
        if "missing" in page:
            return None
        return page
    except Exception as e:
        print(f"Error parsing wiki response: {e}")
        return None


def fuzzy_match(query: str, dataset: list[str]) -> list[str]:
    return get_close_matches(
        query.lower(), [item.lower() for item in dataset], n=15, cutoff=0.6
    )

def build_talent_embed(talent_data: dict) -> discord.Embed:
    embed = discord.Embed(
        title=talent_data.get("name", "Unknown Talent"),
        description=talent_data.get("description", "No description available."),
        color=0x00FF00,
    )
    embed.add_field(
        name="Category", value=talent_data.get("category", "None"), inline=True
    )
    embed.add_field(
        name="Rarity", value=talent_data.get("rarity_type", "Unknown"), inline=True
    )
    embed.add_field(
        name="Requirement", value=talent_data.get("requirement", "None"), inline=False
    )
    bonus = talent_data.get("bonus")
    if bonus and bonus != "N/A":
        embed.add_field(name="Bonus", value=bonus, inline=False)
    hints = talent_data.get("hint", [])
    if hints:
        hints_str = "\n".join(f"- {hint}" for hint in hints)
        embed.add_field(name="Hints", value=hints_str, inline=False)
    return embed

def build_category_embed(category_data: dict) -> discord.Embed:
    embed = discord.Embed(
        title=f"Category: {category_data.get('name', 'Unknown Category')}",
        description=category_data.get(
            "mystic_dialogue", "No mystic dialogue available."
        ),
        color=0x0099FF,
    )
    talents = category_data.get("talents", [])
    if talents:
        lines = []
        for t in talents:
            line = f"**{t.get('name', 'Unknown Talent')}** – *{t.get('rarity_type', 'Unknown')}* | Req: {t.get('requirement', 'None')}"
            lines.append(line)
        talents_str = "\n".join(lines)
    else:
        talents_str = "No talents found in this category."
    embed.add_field(name="Talents", value=talents_str, inline=False)
    return embed


# Optional: Global Paginator Helper for multiple embeds
class Paginator(discord.ui.View):
    def __init__(self, embeds: list[discord.Embed]):
        super().__init__(timeout=60)
        self.embeds = embeds
        self.current = 0

    async def update_message(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            embed=self.embeds[self.current], view=self
        )

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary)
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.current = (self.current - 1) % len(self.embeds)
        await self.update_message(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current = (self.current + 1) % len(self.embeds)
        await self.update_message(interaction)


# ---------------------------------------------------------------------------
# Slash Commands (Global)
# ---------------------------------------------------------------------------
@bot.tree.command(
    name="wiki_boss", description="Fetch Deepwoken boss details from the Wiki."
)
@app_commands.guilds(discord.Object(id=MY_GUILD_ID))
async def wiki_boss(interaction: discord.Interaction, boss_name: str):
    if boss_name.lower() not in [name.lower() for name in BOSSES_LIST]:
        matches = fuzzy_match(boss_name, BOSSES_LIST)
        if len(matches) == 1:
            boss_name = matches[0]
        elif len(matches) > 1:
            description = "Did you mean one of these bosses?\n" + "\n".join(matches)
            embed = discord.Embed(
                title="Multiple Boss Matches", description=description, color=0xFFAA00
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        else:
            await interaction.response.send_message(
                f"No boss found for '{boss_name}'. Check your spelling!", ephemeral=True
            )
            return
    try:
        data = await fetch_wiki_data(boss_name, prop="extracts")
        page = parse_wiki_response(data)
        if not page:
            await interaction.response.send_message(
                f"No data found for boss '{boss_name}'.", ephemeral=True
            )
            return
        description = page.get("extract", "No description available.")

        data_images = await fetch_wiki_data(
            boss_name, prop="images", extra_params={"imlimit": "max", "iiprop": "url"}
        )
        page_images = parse_wiki_response(data_images)
        image_url = None
        if page_images and "images" in page_images:
            images = page_images["images"]
            if images:
                image_url = f"https://static.wikia.nocookie.net/deepwoken/images/{images[0]['title'].replace(' ', '_')}.png"
        embed = discord.Embed(title=boss_name, description=description, color=0x00FF00)
        if image_url:
            embed.set_thumbnail(url=image_url)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(
            f"Error fetching boss data: {e}", ephemeral=True
        )


@bot.tree.command(
    name="wiki_oath", description="Fetch Deepwoken oath details from the Wiki."
)
@app_commands.guilds(discord.Object(id=MY_GUILD_ID))
async def wiki_oath(interaction: discord.Interaction, oath_name: str):
    try:
        data = await fetch_wiki_data(oath_name, prop="extracts")
        page = parse_wiki_response(data)
        if not page:
            await interaction.response.send_message(
                f"No data found for oath '{oath_name}'.", ephemeral=True
            )
            return
        description = page.get("extract", "No description available.")
        embed = discord.Embed(title=oath_name, description=description, color=0x8A2BE2)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(
            f"Error fetching oath data: {e}", ephemeral=True
        )


def load_talents():
    global TALENTS_DATA, CATEGORIES_DATA
    try:
        with open("talents.json", "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        # For each category, store it in CATEGORIES_DATA
        for category in raw_data.get("categories", []):
            cat_name = category.get("name", "Unknown Category")
            CATEGORIES_DATA[cat_name.lower()] = category

            # For each talent in that category, store it in TALENTS_DATA by name
            for talent in category.get("talents", []):
                # Tag the talent with its category so we can display it
                talent["category"] = cat_name
                TALENTS_DATA[talent["name"].lower()] = talent

        print(f"Loaded {len(TALENTS_DATA)} talents and {len(CATEGORIES_DATA)} categories from talents.json")
    except Exception as e:
        print(f"Failed to load talents: {e}")

@bot.tree.command(
    name="talent", description="Show detailed info about a Deepwoken Talent."
)
@app_commands.guilds(discord.Object(id=MY_GUILD_ID))
async def wiki_talent(interaction: discord.Interaction, talent: str ):
    load_talents()
    search_term = talent.lower()
    print(TALENTS_DATA)
    if search_term in TALENTS_DATA:
        embed = build_talent_embed(TALENTS_DATA[search_term])
        await interaction.response.send_message(embed=embed)
        return
    matches = get_close_matches(search_term, TALENTS_DATA.keys(), n=15, cutoff=0.6)
    if not matches:
        await interaction.response.send_message(
            f"No talent found for '{talent}'.", ephemeral=True
        )
        return
    if len(matches) == 1:
        embed = build_talent_embed(TALENTS_DATA[matches[0]])
        await interaction.response.send_message(embed=embed)
    else:
        description = "Did you mean one of these talents?\n" + "\n".join(
            TALENTS_DATA[m]["name"] for m in matches
        )
        embed = discord.Embed(
            title="Multiple Talent Matches", description=description, color=0xFFAA00
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(
    name="wiki_category", description="Show detailed info about a Deepwoken Category."
)
@app_commands.guilds(discord.Object(id=MY_GUILD_ID))
async def wiki_category(interaction: discord.Interaction, category: str):
    search_term = category.lower()
    if search_term in CATEGORIES_DATA:
        embed = build_category_embed(CATEGORIES_DATA[search_term])
        await interaction.response.send_message(embed=embed)
        return
    matches = get_close_matches(search_term, CATEGORIES_DATA.keys(), n=15, cutoff=0.6)
    if not matches:
        await interaction.response.send_message(
            f"No category found for '{category}'.", ephemeral=True
        )
        return
    if len(matches) == 1:
        embed = build_category_embed(CATEGORIES_DATA[matches[0]])
        await interaction.response.send_message(embed=embed)
    else:
        description = "Did you mean one of these categories?\n" + "\n".join(
            CATEGORIES_DATA[m]["name"] for m in matches
        )
        embed = discord.Embed(
            title="Multiple Category Matches", description=description, color=0xFFAA00
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# def extract_deepwoken_id(link: str) -> str | None:
#     match = DEEPWOKEN_LINK_REGEX.match(link)
#     if match:
#         return match.group(1)
#     return None

# async def fetch_build_json(build_id: str) -> dict:
#     """
#     Fetches Deepwoken build data by parsing the HTML of the Next.js page.
#     Raises an exception if the build data cannot be found.
#     """
#     url = f"https://deepwoken.co/builder?id={build_id}"

#     # Use a desktop browser-like User-Agent to avoid minimal or blocked responses
#     headers = {"User-Agent": "Mozilla/5.0"}

#     async with aiohttp.ClientSession() as session:
#         async with session.get(url, headers=headers) as resp:
#             if resp.status != 200:
#                 raise Exception(f"Failed to fetch build. Status code: {resp.status}")
#             html_text = await resp.text()

#     # Try to find the Next.js JSON in a script tag with id="__NEXT_DATA__"
#     match = re.search(
#         r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html_text, re.DOTALL
#     )
#     if not match:
#         # Print out the first 500 chars of the page for debugging
#         snippet = html_text[:500].replace("\n", "\\n")
#         raise Exception(
#             f"No Next.js JSON data found in page HTML.\nDebug snippet:\n{snippet}"
#         )

#     raw_json = match.group(1)

#     # Parse the JSON object
#     try:
#         next_data = json.loads(raw_json)
#     except json.JSONDecodeError as e:
#         raise Exception(f"Failed to parse Next.js data: {e}")

#     # The build data is typically under props.pageProps.buildData
#     build_data = next_data.get("props", {}).get("pageProps", {}).get("buildData")
#     if not build_data:
#         raise Exception("No 'buildData' object found in the Next.js data structure.")

#     return build_data


# def shrine_line(stat_name: str, pre_dict: dict, post_dict: dict) -> str:
#     """
#     Returns a string showing 'preVal (postVal)' if they differ, or just 'val' if they're the same.
#     Example: '15 (20)' or '40'.
#     """
#     pre_val = pre_dict.get(stat_name, 0)
#     post_val = post_dict.get(stat_name, 0)
#     if pre_val == post_val:
#         return str(pre_val)
#     else:
#         return f"{pre_val} ({post_val})"


# def format_shrine_stats(build_data: dict) -> discord.Embed:
#     """
#     Creates a Discord embed comparing preShrine vs postShrine for base, attunement, and weapon.
#     Also shows meta info (Race, Oath, Murmur, etc.).
#     """
#     stats_obj = build_data.get("stats", {})
#     build_name = stats_obj.get("buildName", "Unknown Build")
#     build_desc = stats_obj.get("buildDescription", "")
#     meta_obj = stats_obj.get("meta", {})

#     embed = discord.Embed(
#         title=build_name,
#         description=build_desc,
#         color=0x00FF00,
#         timestamp=datetime.datetime.utcnow(),
#     )
#     embed.set_footer(text="Deepwoken Build")

#     author = build_data.get("author", {})
#     author_name = author.get("name", "Unknown Author")
#     embed.set_author(name=author_name)

#     # Meta information
#     race = meta_obj.get("Race", "None")
#     oath = meta_obj.get("Oath", "None")
#     murmur = meta_obj.get("Murmur", "None")
#     origin = meta_obj.get("Origin", "None")
#     bell = meta_obj.get("Bell", "None")
#     outfit = meta_obj.get("Outfit", "None")

#     meta_str = (
#         f"**Race:** {race}\n"
#         f"**Oath:** {oath}\n"
#         f"**Murmur:** {murmur}\n"
#         f"**Origin:** {origin}\n"
#         f"**Bell:** {bell}\n"
#         f"**Outfit:** {outfit}\n"
#     )
#     embed.add_field(name="Meta", value=meta_str, inline=False)

#     # Pre- and Post-shrine stats
#     pre_shrine = build_data.get("preShrine", {})
#     post_shrine = build_data.get("postShrine", {})

#     pre_base = pre_shrine.get("base", {})
#     pre_attunement = pre_shrine.get("attunement", {})
#     pre_weapon = pre_shrine.get("weapon", {})

#     post_base = post_shrine.get("base", {})
#     post_attunement = post_shrine.get("attunement", {})
#     post_weapon = post_shrine.get("weapon", {})

#     # Base stats embed field
#     base_stat_keys = [
#         "Strength",
#         "Fortitude",
#         "Agility",
#         "Intelligence",
#         "Willpower",
#         "Charisma",
#     ]
#     base_stats_lines = [
#         f"**{stat}:** {shrine_line(stat, pre_base, post_base)}"
#         for stat in base_stat_keys
#     ]
#     embed.add_field(
#         name="Base Stats (Pre -> Post)", value="\n".join(base_stats_lines), inline=False
#     )

#     # Attunement embed field
#     attune_keys = [
#         "Flamecharm",
#         "Frostdraw",
#         "Thundercall",
#         "Galebreathe",
#         "Shadowcast",
#         "Ironsing",
#         "Bloodrend",
#     ]
#     attunement_stats_lines = [
#         f"**{stat}:** {shrine_line(stat, pre_attunement, post_attunement)}"
#         for stat in attune_keys
#     ]
#     embed.add_field(
#         name="Attunements", value="\n".join(attunement_stats_lines), inline=False
#     )

#     # Weapon stats embed field
#     weapon_keys = ["Heavy Wep.", "Medium Wep.", "Light Wep."]
#     weapon_stats_lines = [
#         f"**{stat}:** {shrine_line(stat, pre_weapon, post_weapon)}"
#         for stat in weapon_keys
#     ]
#     embed.add_field(
#         name="Weapon Stats", value="\n".join(weapon_stats_lines), inline=False
#     )

#     return embed


# @bot.tree.command(name="build", description="Submit a Deepwoken build link")
# @app_commands.describe(
#     link="The Deepwoken builder link (e.g. https://deepwoken.co/builder?id=HylA35nm)"
# )
# @app_commands.guilds(discord.Object(id=MY_GUILD_ID))
# async def build_command(interaction: discord.Interaction, link: str):
#     build_id = extract_deepwoken_id(link)
#     if not build_id:
#         await interaction.response.send_message(
#             "Invalid link! Must be like https://deepwoken.co/builder?id=XXXXXXXX",
#             ephemeral=True,
#         )
#         return

#     # Send an initial response to let the user know the build is being processed
#     await interaction.response.send_message("Fetching build data...", ephemeral=True)

#     try:
#         build_data = await fetch_build_json(build_id)
#     except Exception as e:
#         await interaction.followup.send(
#             f"Error fetching build data: {e}", ephemeral=True
#         )
#         return

#     embed = format_shrine_stats(build_data)
#     await interaction.followup.send(embed=embed)


@bot.tree.command(
    name="kickwithrole", description="Kicks members with a selected role."
)
@app_commands.describe(role="Select a role to kick members with that role.")
@app_commands.guilds(discord.Object(id=MY_GUILD_ID))
async def kick_with_role(interaction: discord.Interaction, role: discord.Role):
    # Check if the invoking user has the mod role
    mod_role = discord.utils.get(interaction.guild.roles, name="mod")
    if not mod_role:
        await interaction.response.send_message(
            "Mod role not found in this server.", ephemeral=True
        )
        return
    if mod_role not in interaction.user.roles:
        await interaction.response.send_message(
            "You must have the mod role to use this command.", ephemeral=True
        )
        return

    # Gather members who have the provided role
    to_kick = [member for member in interaction.guild.members if role in member.roles]
    if not to_kick:
        await interaction.response.send_message(
            "No members found with the role.", ephemeral=True
        )
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
    description="Kicks members with no additional roles (only the default @everyone).",
)
@app_commands.guilds(discord.Object(id=MY_GUILD_ID))
async def kick_no_roles(interaction: discord.Interaction):
    # Check if the invoking user has the mod role
    mod_role = discord.utils.get(interaction.guild.roles, name="mod")
    if not mod_role:
        await interaction.response.send_message(
            "Mod role not found in this server.", ephemeral=True
        )
        return
    if mod_role not in interaction.user.roles:
        await interaction.response.send_message(
            "You must have the mod role to use this command.", ephemeral=True
        )
        return

    # Gather members who have no roles other than @everyone
    to_kick = [member for member in interaction.guild.members if len(member.roles) <= 1]
    if not to_kick:
        await interaction.response.send_message(
            "No members found with no additional roles.", ephemeral=True
        )
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


@bot.tree.command(
    name="warn",
    description="Send a warning DM to a selected member and add a warning count.",
)
@app_commands.describe(
    member="Select the member to warn.", message="The warning message to send."
)
@app_commands.guilds(discord.Object(id=MY_GUILD_ID))
async def warn(interaction: discord.Interaction, member: discord.Member, message: str):
    mod_role = discord.utils.get(interaction.guild.roles, name="mod")
    if not mod_role:
        await interaction.response.send_message(
            "Mod role not found in this server.", ephemeral=True
        )
        return
    if mod_role not in interaction.user.roles:
        await interaction.response.send_message(
            "You must have the mod role to use this command.", ephemeral=True
        )
        return

    try:
        warn_embed = discord.Embed(
            title="You have received a warning",
            description=f"Please take note that you have been warned in **{interaction.guild.name}**.",
            color=discord.Color.orange(),
        )
        warn_embed.add_field(name="Warning Details", value=message, inline=False)
        warn_embed.set_footer(
            text="Please adhere to the server rules to avoid further actions."
        )

        if SERVER_ICON_URL:
            warn_embed.set_thumbnail(url=SERVER_ICON_URL)
        else:
            if interaction.guild.icon:
                warn_embed.set_thumbnail(url=interaction.guild.icon.url)

        try:
            await member.send(embed=warn_embed)
        except Exception as dm_error:
            print(f"Could not send DM to {member}: {dm_error}")
            await interaction.response.send_message(
                f"Warning not delivered. Could not DM {member.mention}.", ephemeral=True
            )
            return

        # **New code:** Increment the warning count in the same User table

        await interaction.response.send_message(
            f"Sent warning to {member.mention}.", ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f"Failed to send warning to {member.mention}: {e}", ephemeral=True
        )


# RESOLVE MEMBER
def resolve_member(guild: discord.Guild, member_str: str) -> discord.Member | None:
    """Attempt to resolve a member from a string (mention, ID, or name)."""
    # Check if it's a mention: <@!1234567890> or <@1234567890>
    mention_match = re.match(r"<@!?(\d+)>", member_str)
    if mention_match:
        member_id = int(mention_match.group(1))
        return guild.get_member(member_id)
    # Check if it's a numeric ID
    try:
        member_id = int(member_str)
        return guild.get_member(member_id)
    except ValueError:
        pass
    # Otherwise, try a case-insensitive name search
    return discord.utils.find(
        lambda m: member_str.lower() in m.name.lower(), guild.members
    )


@bot.tree.command(name="kick", description="Kick a selected member from the server.")
@app_commands.describe(
    member="Member name, ID, or mention to kick.", reason="Optional reason for kicking."
)
@app_commands.guilds(discord.Object(id=MY_GUILD_ID))
async def kick(interaction: discord.Interaction, member: str, reason: str = ""):
    # Resolve the member manually
    resolved_member = resolve_member(interaction.guild, member)
    if not resolved_member:
        await interaction.response.send_message(
            f"Could not resolve member: `{member}`. Please use a valid mention, ID, or name.",
            ephemeral=True,
        )
        return

    # Check if the invoking user has the mod role
    mod_role = discord.utils.get(interaction.guild.roles, name="mod")
    if not mod_role:
        await interaction.response.send_message(
            "Mod role not found in this server.", ephemeral=True
        )
        return
    if mod_role not in interaction.user.roles:
        await interaction.response.send_message(
            "You must have the mod role to use this command.", ephemeral=True
        )
        return

    # If no reason is given, assign a default message.
    if not reason.strip():
        reason = (
            "This is an automated message. You have been automatically kicked due to inactivity. "
            "It's nothing personal, but we wish to have active people in the server."
        )

    try:
        # Build the DM embed
        dm_embed = discord.Embed(
            title="You have been removed from the server",
            description=f"Unfortunately, you have been kicked from **{interaction.guild.name}**.",
            color=discord.Color.red(),
        )
        dm_embed.add_field(name="Reason", value=reason, inline=False)
        dm_embed.set_footer(
            text="We apologize for any inconvenience this may have caused."
        )

        try:
            await resolved_member.send(embed=dm_embed)
        except Exception as dm_error:
            print(f"Could not send DM to {resolved_member}: {dm_error}")

        # Kick the member
        await resolved_member.kick(reason=reason)
        await interaction.response.send_message(
            f"Kicked {resolved_member.mention} for reason: {reason}", ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f"Failed to kick {resolved_member.mention}: {e}", ephemeral=True
        )


# --------------------------------------------------------------------------
# Data Loading for Talents and Categories
# --------------------------------------------------------------------------
# TALENTS_DATA = {}
# CATEGORIES_DATA = {}

# def load_talents():
#     global TALENTS_DATA, CATEGORIES_DATA
#     try:
#         with open("talents.json", "r", encoding="utf-8") as f:
#             raw_data = json.load(f)
#         for category in raw_data.get("categories", []):
#             cat_name = category.get("name", "Unknown Category")
#             CATEGORIES_DATA[cat_name.lower()] = category
#             for talent in category.get("talents", []):
#                 talent["category"] = cat_name
#                 TALENTS_DATA[talent["name"].lower()] = talent
#         print(f"Loaded {len(TALENTS_DATA)} talents and {len(CATEGORIES_DATA)} categories from talents.json")
#     except Exception as e:
#         print(f"Failed to load talents: {e}")

# load_talents()

# # --------------------------------------------------------------------------
# # Embed Builders and Match Suggestion Embed
# # --------------------------------------------------------------------------
# def build_talent_embed(talent_data: dict) -> discord.Embed:
#     """
#     Given a single talent's data, return a Discord Embed.
#     """
#     embed = discord.Embed(
#         title=talent_data.get("name", "Unknown Talent"),
#         description=talent_data.get("description", "No description available."),
#         color=0x00FF00
#     )
#     embed.add_field(name="Category", value=talent_data.get("category", "None"), inline=True)
#     embed.add_field(name="Rarity", value=talent_data.get("rarity_type", "Unknown"), inline=True)
#     embed.add_field(name="Requirement", value=talent_data.get("requirement", "None"), inline=False)
#     bonus = talent_data.get("bonus")
#     if bonus and bonus != "N/A":
#         embed.add_field(name="Bonus", value=bonus, inline=False)
#     cooldown = talent_data.get("cooldown", "None")
#     embed.add_field(name="Cooldown", value=cooldown, inline=False)
#     hints = talent_data.get("hint", [])
#     if hints:
#         hints_str = "\n".join(f"- {hint}" for hint in hints)
#         embed.add_field(name="Hints", value=hints_str, inline=False)
#     return embed

# def create_match_embed(match_type: str, matches: list, is_category: bool = False) -> discord.Embed:
#     """
#     Create an embed listing multiple matches in a more readable format.
#     match_type: "Talent" or "Category"
#     matches: list of lowercase keys
#     is_category: whether these matches are categories or talents
#     """
#     title = f"Multiple {match_type} Matches Found"
#     if is_category:
#         lines = [f"• {CATEGORIES_DATA[m]['name']}" for m in matches]
#     else:
#         lines = [f"• {TALENTS_DATA[m]['name']}" for m in matches]
#     lines_str = "\n".join(lines)
#     description = (
#         f"**Did you mean one of these {match_type.lower()}s?**\n\n"
#         f"{lines_str}\n\n"
#         f"**Please type the full name!**"
#     )
#     return discord.Embed(title=title, description=description, color=0xFFAA00)

# def build_category_embed(category_data: dict) -> discord.Embed:
#     """
#     Given a category's data, return a Discord Embed that lists the talents in a compact format.
#     Each talent is shown on one line with its name, rarity, and requirement.
#     """
#     cat_name = category_data.get("name", "Unknown Category")
#     mystic_dialogue = category_data.get("mystic_dialogue", "No mystic dialogue available.")

#     embed = discord.Embed(
#         title=f"Category: {cat_name}",
#         description=mystic_dialogue,
#         color=0x0099FF
#     )

#     talents = category_data.get("talents", [])
#     if talents:
#         lines = []
#         for t in talents:
#             t_name = t.get("name", "Unknown Talent")
#             t_rarity = t.get("rarity_type", "Unknown")
#             t_req = t.get("requirement", "None")
#             line = f"**{t_name}** – *{t_rarity}* | Req: {t_req}"
#             lines.append(line)
#         talents_str = "\n".join(lines)
#     else:
#         talents_str = "No talents found in this category."

#     embed.add_field(name="Talents", value=talents_str, inline=False)
#     return embed

# # --------------------------------------------------------------------------
# #  /talent Command
# # --------------------------------------------------------------------------
# @bot.tree.command(name="talent", description="Show detailed info about a Deepwoken Talent.")
# @app_commands.describe(talent="Name of the talent you want info about.")
# @app_commands.guilds(discord.Object(id=MY_GUILD_ID))
# async def slash_talent(interaction: discord.Interaction, talent: str):
#     search_term = talent.lower()

#     # 1) Exact match
#     if search_term in TALENTS_DATA:
#         await interaction.response.send_message(embed=build_talent_embed(TALENTS_DATA[search_term]))
#         return

#     # 2) Partial matches (up to 15)
#     partial_matches = [name for name in TALENTS_DATA if search_term in name]
#     if partial_matches:
#         if len(partial_matches) == 1:
#             await interaction.response.send_message(embed=build_talent_embed(TALENTS_DATA[partial_matches[0]]))
#             return
#         elif 2 <= len(partial_matches) <= 15:
#             embed = create_match_embed("Talent", partial_matches, is_category=False)
#             await interaction.response.send_message(embed=embed)
#             return
#         else:
#             await interaction.response.send_message("Too many results. Please be more specific!")
#             return

#     # 3) Fuzzy matching (up to 15)
#     fuzzy_matches = get_close_matches(search_term, TALENTS_DATA.keys(), n=15, cutoff=0.6)
#     if not fuzzy_matches:
#         await interaction.response.send_message(f"No talent found for '{talent}'. Check your spelling!")
#         return

#     if len(fuzzy_matches) == 1:
#         await interaction.response.send_message(embed=build_talent_embed(TALENTS_DATA[fuzzy_matches[0]]))
#     elif 2 <= len(fuzzy_matches) <= 15:
#         embed = create_match_embed("Talent", fuzzy_matches, is_category=False)
#         await interaction.response.send_message(embed=embed)
#     else:
#         await interaction.response.send_message("Too many possible matches. Please be more specific!")

# # --------------------------------------------------------------------------
# #  /category Command (detailed)
# # --------------------------------------------------------------------------
# @bot.tree.command(name="category", description="Show detailed info about a Deepwoken Category.")
# @app_commands.describe(category="Name of the category you want info about.")
# @app_commands.guilds(discord.Object(id=MY_GUILD_ID))
# async def slash_category(interaction: discord.Interaction, category: str):
#     search_term = category.lower()

#     # 1) Exact match
#     if search_term in CATEGORIES_DATA:
#         embed = build_category_embed(CATEGORIES_DATA[search_term])
#         await interaction.response.send_message(embed=embed)
#         return

#     # 2) Partial matches (up to 15)
#     partial_matches = [cat for cat in CATEGORIES_DATA if search_term in cat]
#     if partial_matches:
#         if len(partial_matches) == 1:
#             embed = build_category_embed(CATEGORIES_DATA[partial_matches[0]])
#             await interaction.response.send_message(embed=embed)
#             return
#         elif 2 <= len(partial_matches) <= 15:
#             embed = create_match_embed("Category", partial_matches, is_category=True)
#             await interaction.response.send_message(embed=embed)
#             return
#         else:
#             await interaction.response.send_message("Too many results. Please be more specific!")
#             return

#     # 3) Fuzzy matching (up to 15)
#     fuzzy_matches = get_close_matches(search_term, CATEGORIES_DATA.keys(), n=15, cutoff=0.6)
#     if not fuzzy_matches:
#         await interaction.response.send_message(f"No category found for '{category}'. Check your spelling!")
#         return

#     if len(fuzzy_matches) == 1:
#         embed = build_category_embed(CATEGORIES_DATA[fuzzy_matches[0]])
#         await interaction.response.send_message(embed=embed)
#     elif 2 <= len(fuzzy_matches) <= 15:
#         embed = create_match_embed("Category", fuzzy_matches, is_category=True)
#         await interaction.response.send_message(embed=embed)
#     else:
#         await interaction.response.send_message("Too many possible matches. Please be more specific!")

# OATHS_DATA = {}

# def load_oaths():
#     global OATHS_DATA
#     try:
#         with open("oaths.json", "r", encoding="utf-8") as f:
#             data = json.load(f)
#         for oath in data.get("oaths", []):
#             OATHS_DATA[oath["name"].lower()] = oath
#         print(f"Loaded {len(OATHS_DATA)} oaths from oaths.json")
#     except Exception as e:
#         print(f"Failed to load oaths: {e}")

# load_oaths()

# def build_oath_embed(oath_data: dict) -> discord.Embed:
#     """Builds a beautiful embed to display the oath information."""
#     embed = discord.Embed(
#         title=f"Oath: {oath_data.get('name', 'Unknown Oath')}",
#         description=oath_data.get("description", "No description available."),
#         color=0x8A2BE2,  # A pleasant purple color
#         timestamp=discord.utils.utcnow()
#     )

#     # Oath Requirement
#     requirement = oath_data.get("oath_requirement", "None")
#     embed.add_field(name="Oath Requirement", value=requirement, inline=False)

#     # Obtainment (list of steps)
#     obtainment = oath_data.get("obtainment", [])
#     if obtainment:
#         obtainment_str = "\n".join(obtainment)
#         embed.add_field(name="Obtainment", value=obtainment_str, inline=False)

#     # Progression (if available)
#     progression = oath_data.get("progression")
#     if progression:
#         embed.add_field(name="Progression", value=progression, inline=False)

#     # Effects
#     effects = oath_data.get("effects", [])
#     if effects:
#         embed.add_field(name="Effects", value="\n".join(effects), inline=False)

#     # Abilities – combine mantras and talents if available
#     abilities = oath_data.get("abilities", {})
#     abilities_lines = []
#     if "mantras" in abilities and abilities["mantras"]:
#         abilities_lines.append("**Mantras:**")
#         abilities_lines.extend(f"• {m}" for m in abilities["mantras"])
#     if "talents" in abilities and abilities["talents"]:
#         abilities_lines.append("\n**Talents:**")
#         abilities_lines.extend(f"• {t}" for t in abilities["talents"])
#     if abilities_lines:
#         embed.add_field(name="Abilities", value="\n".join(abilities_lines), inline=False)

#     # Trivia
#     trivia = oath_data.get("trivia", [])
#     if trivia:
#         embed.add_field(name="Trivia", value="\n".join(trivia), inline=False)

#     # References
#     references = oath_data.get("references", [])
#     if references:
#         embed.add_field(name="References", value="\n".join(references), inline=False)

#     # Navigation – if provided
#     navigation = oath_data.get("navigation", "N/A")
#     embed.add_field(name="Navigation", value=navigation, inline=False)

#     # Mystic Quote (as footer)
#     mystic_quote = oath_data.get("mystic_quote")
#     if mystic_quote:
#         embed.set_footer(text=mystic_quote)

#     return embed

# # Slash command for oaths
# @bot.tree.command(name="oath", description="Show detailed info about a Deepwoken Oath.")
# @app_commands.describe(oath="Name of the oath you want info about.")
# @app_commands.guilds(discord.Object(id=MY_GUILD_ID))
# async def slash_oath(interaction: discord.Interaction, oath: str):
#     search_term = oath.lower()

#     # 1) Exact match
#     if search_term in OATHS_DATA:
#         embed = build_oath_embed(OATHS_DATA[search_term])
#         await interaction.response.send_message(embed=embed)
#         return

#     # 2) Partial matches
#     partial_matches = [name for name in OATHS_DATA if search_term in name]
#     if partial_matches:
#         if len(partial_matches) == 1:
#             embed = build_oath_embed(OATHS_DATA[partial_matches[0]])
#             await interaction.response.send_message(embed=embed)
#             return
#         elif 2 <= len(partial_matches) <= 15:
#             # Use the match embed helper (reusing our similar style)
#             lines = [f"• {OATHS_DATA[m]['name']}" for m in partial_matches]
#             embed = discord.Embed(
#                 title="Multiple Oath Matches Found",
#                 description=f"**Did you mean one of these oaths?**\n\n{chr(10).join(lines)}\n\nPlease type the full oath name!",
#                 color=0xFFAA00
#             )
#             await interaction.response.send_message(embed=embed)
#             return
#         else:
#             await interaction.response.send_message("Too many results. Please be more specific!", ephemeral=True)
#             return

#     # 3) Fuzzy matching
#     fuzzy_matches = get_close_matches(search_term, OATHS_DATA.keys(), n=15, cutoff=0.6)
#     if not fuzzy_matches:
#         await interaction.response.send_message(f"No oath found for '{oath}'. Check your spelling!", ephemeral=True)
#         return
#     if len(fuzzy_matches) == 1:
#         embed = build_oath_embed(OATHS_DATA[fuzzy_matches[0]])
#         await interaction.response.send_message(embed=embed)
#     elif 2 <= len(fuzzy_matches) <= 15:
#         lines = [f"• {OATHS_DATA[m]['name']}" for m in fuzzy_matches]
#         embed = discord.Embed(
#             title="Multiple Oath Matches Found",
#             description=f"**Did you mean one of these oaths?**\n\n{chr(10).join(lines)}\n\nPlease type the full oath name!",
#             color=0xFFAA00
#         )
#         await interaction.response.send_message(embed=embed)
#     else:
#         await interaction.response.send_message("Too many possible matches. Please be more specific!", ephemeral=True)

# keep_alive()

bot.run(DISCORD_TOKEN)
