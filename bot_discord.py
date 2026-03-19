"""
╔══════════════════════════════════════════════════════════════════╗
║              BOT DISCORD COMPLET - TOUT-EN-UN                   ║
║  Tickets | Modération | Logs | Auto-rôles | Règlement           ║
╚══════════════════════════════════════════════════════════════════╝

INSTALLATION :
    pip install discord.py

CONFIGURATION :
    1. Remplace TOKEN par ton token de bot Discord
    2. Remplace les IDs selon ton serveur
    3. Lance : python bot_discord.py
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import datetime
import aiohttp
import json
import os
from TikTokLive import TikTokLiveClient
from TikTokLive.client.errors import UserOfflineError, UserNotFoundError
import json
import os

# ══════════════════════════════════════════════════
#                  CONFIGURATION
# ══════════════════════════════════════════════════

TOKEN ="DISCORD_TOKEN"  # ← Remplace par ton token

# IDs à configurer (clic droit → Copier l'ID avec le mode développeur activé)
GUILD_ID           = 1478563485221654599   # ID de ton serveur
LOG_CHANNEL_ID     = 1478566350543654942   # Salon pour les logs de modération
TICKET_CATEGORY_ID = 1478566320407711754   # Catégorie où créer les tickets
STAFF_ROLE_ID      = 1478566245321408687   # Rôle du staff (peut voir/gérer les tickets)
MUTED_ROLE_ID      = 1479139951370305599   # Rôle "Muted" (crée-le manuellement)
WELCOME_CHANNEL_ID = 1478571275960979476   # Salon de bienvenue
AUTO_ROLE_ID       = 1479154707627770128   # Rôle donné automatiquement à l'arrivée
RULES_CHANNEL_ID   = 1478566324140507400   # Salon #règlement
MEMBER_ROLE_ID     = 1478566255127560222   # Rôle donné après acceptation du règlement
TIKTOK_NOTIF_CHANNEL_ID = 1483893520296050769   # ← Remplace par l'ID du salon de notifs TikTok
TIKTOK_CHECK_INTERVAL   = 60              # Vérification toutes les 60 secondes

# Couleurs embed
COLOR_SUCCESS = 0x2ECC71
COLOR_ERROR   = 0xE74C3C
COLOR_INFO    = 0x3498DB
COLOR_WARNING = 0xF39C12
COLOR_MOD     = 0x9B59B6

# ══════════════════════════════════════════════════
#                INITIALISATION
# ══════════════════════════════════════════════════

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Stockage en mémoire
muted_users    = {}
warnings       = {}
open_tickets   = {}
ticket_counter = [0]

# Surveillance TikTok
TIKTOK_SAVE_FILE = "tiktok_users.json"

def load_tiktok_users() -> set:
    if os.path.exists(TIKTOK_SAVE_FILE):
        try:
            with open(TIKTOK_SAVE_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()

def save_tiktok_users():
    with open(TIKTOK_SAVE_FILE, "w") as f:
        json.dump(list(tiktok_users), f, indent=2)

tiktok_users         = load_tiktok_users()  # chargé depuis tiktok_users.json
tiktok_live_notified = set()                # anti-doublon (remis à zéro au démarrage)

# ══════════════════════════════════════════════════
#              UTILITAIRES / HELPERS
# ══════════════════════════════════════════════════

async def send_log(guild: discord.Guild, embed: discord.Embed):
    channel = guild.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(embed=embed)

def make_embed(title: str, description: str, color: int, member: discord.Member = None) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color,
                          timestamp=datetime.datetime.utcnow())
    if member:
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"ID : {member.id}")
    return embed

# ══════════════════════════════════════════════════
#               ÉVÉNEMENTS PRINCIPAUX
# ══════════════════════════════════════════════════

@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user} (ID: {bot.user.id})")
    print(f"   Serveurs : {len(bot.guilds)}")
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="le serveur 👀")
    )
    try:
        guild = discord.Object(id=GUILD_ID)
        tree.copy_global_to(guild=guild)
        synced = await tree.sync(guild=guild)
        print(f"   Commandes slash synchronisées : {len(synced)}")
    except Exception as e:
        print(f"   Erreur sync : {e}")
    check_tiktok_lives.start()


@bot.event
async def on_member_join(member: discord.Member):
    role = member.guild.get_role(AUTO_ROLE_ID)
    if role:
        try:
            await member.add_roles(role, reason="Auto-rôle à l'arrivée")
        except discord.Forbidden:
            pass

    channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        embed = discord.Embed(
            title="🎉 Nouveau membre !",
            description=(
                f"Bienvenue **{member.mention}** sur **{member.guild.name}** !\n\n"
                f"Tu es le **{member.guild.member_count}ème** membre.\n"
                f"Pense à lire le règlement et bonne ambiance ! 🚀"
            ),
            color=COLOR_SUCCESS
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Rejoint le {datetime.datetime.now().strftime('%d/%m/%Y à %H:%M')}")
        await channel.send(embed=embed)

    await send_log(member.guild, make_embed(
        "📥 Membre rejoint", f"**{member}** a rejoint le serveur.", COLOR_INFO, member
    ))


@bot.event
async def on_member_remove(member: discord.Member):
    await send_log(member.guild, make_embed(
        "📤 Membre parti", f"**{member}** a quitté le serveur.", COLOR_WARNING, member
    ))


@bot.event
async def on_message_delete(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    embed = make_embed(
        "🗑️ Message supprimé",
        f"**Auteur :** {message.author.mention}\n"
        f"**Salon :** {message.channel.mention}\n"
        f"**Contenu :** {message.content[:1000] or '*vide / média*'}",
        COLOR_WARNING, message.author
    )
    await send_log(message.guild, embed)


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if before.author.bot or before.content == after.content or not before.guild:
        return
    embed = make_embed(
        "✏️ Message modifié",
        f"**Auteur :** {before.author.mention}\n"
        f"**Salon :** {before.channel.mention}\n"
        f"**Avant :** {before.content[:500]}\n"
        f"**Après :** {after.content[:500]}",
        COLOR_INFO, before.author
    )
    await send_log(before.guild, embed)


@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    await send_log(guild, make_embed(
        "🔨 Membre banni", f"**{user}** a été banni du serveur.", COLOR_ERROR
    ))


@bot.event
async def on_member_unban(guild: discord.Guild, user: discord.User):
    await send_log(guild, make_embed(
        "✅ Membre débanni", f"**{user}** a été débanni.", COLOR_SUCCESS
    ))

# ══════════════════════════════════════════════════
#        SYSTÈME D'ACCEPTATION DU RÈGLEMENT
# ══════════════════════════════════════════════════

class RulesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ J'ai lu et j'accepte le règlement",
                       style=discord.ButtonStyle.success,
                       custom_id="accept_rules")
    async def accept_rules(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Répond immédiatement à Discord pour éviter "échec de l'interaction"
        await interaction.response.defer(ephemeral=True)

        member = interaction.user
        guild  = interaction.guild
        role   = guild.get_role(MEMBER_ROLE_ID)

        if not role:
            await interaction.followup.send(
                "❌ Rôle introuvable, contacte un admin.", ephemeral=True
            )
            return

        if role in member.roles:
            await interaction.followup.send(
                "✅ Tu as déjà accepté le règlement !", ephemeral=True
            )
            return

        try:
            await member.add_roles(role, reason="Règlement accepté")
            await interaction.followup.send(
                "🎉 Bienvenue ! Tu as maintenant accès à tous les salons.", ephemeral=True
            )
            await send_log(guild, make_embed(
                "📋 Règlement accepté",
                f"**{member}** a accepté le règlement.",
                COLOR_SUCCESS, member
            ))
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Erreur de permissions. Le rôle du bot doit être au-dessus du rôle Membre.", ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Une erreur est survenue : {e}", ephemeral=True
            )


@tree.command(name="setup-reglement", description="[Admin] Envoie le message du règlement avec bouton")
@app_commands.checks.has_permissions(administrator=True)
async def setup_reglement(interaction: discord.Interaction,
                           titre: str = "📋 Règlement du serveur",
                           contenu: str = "Lis le règlement et clique sur le bouton pour accéder au serveur."):
    embed = discord.Embed(
        title=titre,
        description=contenu,
        color=COLOR_INFO,
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_footer(text="En cliquant, tu acceptes les règles du serveur.")
    await interaction.channel.send(embed=embed, view=RulesView())
    await interaction.response.send_message("✅ Message de règlement envoyé !", ephemeral=True)

# ══════════════════════════════════════════════════
#          SYSTÈME DE TICKETS (SLASH + BOUTONS)
# ══════════════════════════════════════════════════

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Ouvrir un ticket", style=discord.ButtonStyle.primary,
                       custom_id="open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        guild  = interaction.guild
        member = interaction.user

        for ch_id, uid in open_tickets.items():
            if uid == member.id:
                ch = guild.get_channel(ch_id)
                if ch:
                    await interaction.followup.send(
                        f"❌ Tu as déjà un ticket ouvert : {ch.mention}", ephemeral=True
                    )
                    return

        ticket_counter[0] += 1
        category   = guild.get_channel(TICKET_CATEGORY_ID)
        staff_role = guild.get_role(STAFF_ROLE_ID)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True,
                                                 attach_files=True, embed_links=True),
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(
                read_messages=True, send_messages=True, manage_messages=True
            )

        try:
            channel = await guild.create_text_channel(
                name=f"ticket-{ticket_counter[0]:04d}-{member.name}",
                category=category,
                overwrites=overwrites,
                topic=f"Ticket de {member} | ID: {member.id}"
            )

            open_tickets[channel.id] = member.id

            embed = discord.Embed(
                title=f"🎫 Ticket #{ticket_counter[0]:04d}",
                description=(
                    f"Bienvenue {member.mention} !\n\n"
                    f"Décris ton problème et le staff te répondra dès que possible.\n\n"
                    f"Pour fermer ce ticket, clique sur **Fermer le ticket** ci-dessous."
                ),
                color=COLOR_INFO,
                timestamp=datetime.datetime.utcnow()
            )
            embed.set_footer(text=f"Ouvert par {member}")

            staff_mention = staff_role.mention if staff_role else ""
            await channel.send(content=staff_mention, embed=embed, view=TicketManageView())
            await interaction.followup.send(
                f"✅ Ton ticket a été créé : {channel.mention}", ephemeral=True
            )
            await send_log(guild, make_embed(
                "🎫 Ticket ouvert",
                f"**{member}** a ouvert le ticket {channel.mention}",
                COLOR_INFO, member
            ))
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Impossible de créer le ticket. Vérifie les permissions du bot.", ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Erreur : {e}", ephemeral=True
            )


class TicketManageView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Fermer le ticket", style=discord.ButtonStyle.danger,
                       custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel    = interaction.channel
        guild      = interaction.guild
        staff_role = guild.get_role(STAFF_ROLE_ID)
        is_staff   = staff_role in interaction.user.roles if staff_role else False
        is_owner   = open_tickets.get(channel.id) == interaction.user.id

        if not is_staff and not is_owner:
            await interaction.response.send_message("❌ Tu n'as pas la permission.", ephemeral=True)
            return

        await interaction.response.send_message("🔒 Fermeture du ticket dans 5 secondes...")
        await asyncio.sleep(5)

        opener_id = open_tickets.pop(channel.id, None)
        opener    = guild.get_member(opener_id) if opener_id else None
        await send_log(guild, make_embed(
            "🔒 Ticket fermé",
            f"Ticket **{channel.name}** fermé par **{interaction.user}**"
            + (f" (ouvert par **{opener}**)" if opener else ""),
            COLOR_WARNING
        ))
        await channel.delete(reason=f"Ticket fermé par {interaction.user}")

    @discord.ui.button(label="📌 Claim", style=discord.ButtonStyle.secondary,
                       custom_id="claim_ticket")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        staff_role = interaction.guild.get_role(STAFF_ROLE_ID)
        if staff_role not in interaction.user.roles:
            await interaction.response.send_message("❌ Réservé au staff.", ephemeral=True)
            return
        await interaction.channel.edit(topic=f"{interaction.channel.topic} | Pris en charge par {interaction.user}")
        await interaction.response.send_message(
            f"📌 Ticket pris en charge par {interaction.user.mention} !"
        )


@tree.command(name="setup-tickets", description="[Staff] Envoie le panneau de création de tickets")
@app_commands.checks.has_permissions(administrator=True)
async def setup_tickets(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎫 Support | Ouvre un ticket",
        description=(
            "Pour contacter le staff ou obtenir de l'aide,\n"
            "clique sur le bouton ci-dessous pour ouvrir un ticket privé.\n\n"
            "⚠️ N'abuse pas du système de tickets."
        ),
        color=COLOR_INFO
    )
    await interaction.channel.send(embed=embed, view=TicketView())
    await interaction.response.send_message("✅ Panneau de tickets envoyé !", ephemeral=True)

# ══════════════════════════════════════════════════
#              COMMANDES DE MODÉRATION
# ══════════════════════════════════════════════════

@tree.command(name="kick", description="[Mod] Expulse un membre")
@app_commands.describe(membre="Membre à expulser", raison="Raison de l'expulsion")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, membre: discord.Member, raison: str = "Aucune raison"):
    if membre.top_role >= interaction.user.top_role:
        await interaction.response.send_message("❌ Tu ne peux pas kick ce membre.", ephemeral=True)
        return
    try:
        await membre.send(embed=make_embed(
            "👢 Tu as été expulsé",
            f"**Serveur :** {interaction.guild.name}\n**Raison :** {raison}",
            COLOR_ERROR
        ))
    except:
        pass
    await membre.kick(reason=f"{raison} | Par {interaction.user}")
    embed = make_embed("👢 Membre expulsé", f"**{membre}** expulsé par {interaction.user.mention}\n**Raison :** {raison}", COLOR_WARNING, membre)
    await interaction.response.send_message(embed=embed)
    await send_log(interaction.guild, embed)


@tree.command(name="ban", description="[Mod] Bannit un membre")
@app_commands.describe(membre="Membre à bannir", raison="Raison du ban", supprimer_messages="Jours de messages à supprimer (0-7)")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, membre: discord.Member, raison: str = "Aucune raison", supprimer_messages: int = 0):
    if membre.top_role >= interaction.user.top_role:
        await interaction.response.send_message("❌ Tu ne peux pas bannir ce membre.", ephemeral=True)
        return
    try:
        await membre.send(embed=make_embed(
            "🔨 Tu as été banni",
            f"**Serveur :** {interaction.guild.name}\n**Raison :** {raison}",
            COLOR_ERROR
        ))
    except:
        pass
    await membre.ban(reason=f"{raison} | Par {interaction.user}", delete_message_days=min(supprimer_messages, 7))
    embed = make_embed("🔨 Membre banni", f"**{membre}** banni par {interaction.user.mention}\n**Raison :** {raison}", COLOR_ERROR, membre)
    await interaction.response.send_message(embed=embed)
    await send_log(interaction.guild, embed)


@tree.command(name="unban", description="[Mod] Débannit un utilisateur")
@app_commands.describe(user_id="ID de l'utilisateur à débannir")
@app_commands.checks.has_permissions(ban_members=True)
async def unban(interaction: discord.Interaction, user_id: str):
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user)
        embed = make_embed("✅ Membre débanni", f"**{user}** a été débanni.", COLOR_SUCCESS)
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)


@tree.command(name="mute", description="[Mod] Réduit au silence un membre")
@app_commands.describe(membre="Membre à mute", duree="Durée en minutes (0 = permanent)", raison="Raison")
@app_commands.checks.has_permissions(manage_roles=True)
async def mute(interaction: discord.Interaction, membre: discord.Member, duree: int = 0, raison: str = "Aucune raison"):
    muted_role = interaction.guild.get_role(MUTED_ROLE_ID)
    if not muted_role:
        await interaction.response.send_message("❌ Rôle 'Muted' introuvable.", ephemeral=True)
        return
    await membre.add_roles(muted_role, reason=f"{raison} | Par {interaction.user}")
    duree_text = f"{duree} minute(s)" if duree > 0 else "permanent"
    embed = make_embed("🔇 Membre mute", f"**{membre}** mute par {interaction.user.mention}\n**Durée :** {duree_text}\n**Raison :** {raison}", COLOR_WARNING, membre)
    await interaction.response.send_message(embed=embed)
    await send_log(interaction.guild, embed)
    if duree > 0:
        muted_users[membre.id] = datetime.datetime.utcnow() + datetime.timedelta(minutes=duree)
        await asyncio.sleep(duree * 60)
        if membre.id in muted_users:
            await membre.remove_roles(muted_role, reason="Mute expiré")
            del muted_users[membre.id]


@tree.command(name="unmute", description="[Mod] Retire le mute d'un membre")
@app_commands.describe(membre="Membre à unmute")
@app_commands.checks.has_permissions(manage_roles=True)
async def unmute(interaction: discord.Interaction, membre: discord.Member):
    muted_role = interaction.guild.get_role(MUTED_ROLE_ID)
    if not muted_role or muted_role not in membre.roles:
        await interaction.response.send_message("❌ Ce membre n'est pas mute.", ephemeral=True)
        return
    await membre.remove_roles(muted_role, reason=f"Unmute par {interaction.user}")
    muted_users.pop(membre.id, None)
    embed = make_embed("🔊 Membre unmute", f"**{membre}** unmute par {interaction.user.mention}", COLOR_SUCCESS, membre)
    await interaction.response.send_message(embed=embed)
    await send_log(interaction.guild, embed)


@tree.command(name="warn", description="[Mod] Avertit un membre")
@app_commands.describe(membre="Membre à avertir", raison="Raison de l'avertissement")
@app_commands.checks.has_permissions(manage_messages=True)
async def warn(interaction: discord.Interaction, membre: discord.Member, raison: str):
    if membre.id not in warnings:
        warnings[membre.id] = []
    warnings[membre.id].append({
        "raison": raison,
        "par": str(interaction.user),
        "date": datetime.datetime.utcnow().strftime("%d/%m/%Y %H:%M")
    })
    count = len(warnings[membre.id])
    try:
        await membre.send(embed=make_embed(
            "⚠️ Avertissement",
            f"**Serveur :** {interaction.guild.name}\n**Raison :** {raison}\n**Total warnings :** {count}",
            COLOR_WARNING
        ))
    except:
        pass
    embed = make_embed("⚠️ Avertissement", f"**{membre}** averti par {interaction.user.mention}\n**Raison :** {raison}\n**Total warnings :** {count}", COLOR_WARNING, membre)
    await interaction.response.send_message(embed=embed)
    await send_log(interaction.guild, embed)
    if count >= 3:
        muted_role = interaction.guild.get_role(MUTED_ROLE_ID)
        if muted_role:
            await membre.add_roles(muted_role, reason="3 warnings — mute automatique")
            await interaction.channel.send(f"🔇 **{membre}** a été automatiquement mute pour 3 warnings.")


@tree.command(name="warnings", description="Affiche les avertissements d'un membre")
@app_commands.describe(membre="Membre dont voir les warnings")
async def show_warnings(interaction: discord.Interaction, membre: discord.Member):
    user_warnings = warnings.get(membre.id, [])
    if not user_warnings:
        await interaction.response.send_message(f"✅ **{membre}** n'a aucun avertissement.", ephemeral=True)
        return
    desc = "\n".join([f"`{i+1}.` {w['raison']} — par **{w['par']}** le {w['date']}"
                      for i, w in enumerate(user_warnings)])
    embed = make_embed(f"⚠️ Warnings de {membre}", desc, COLOR_WARNING, membre)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="clearwarn", description="[Mod] Efface les warnings d'un membre")
@app_commands.describe(membre="Membre à nettoyer")
@app_commands.checks.has_permissions(manage_messages=True)
async def clearwarn(interaction: discord.Interaction, membre: discord.Member):
    warnings.pop(membre.id, None)
    await interaction.response.send_message(f"✅ Warnings de **{membre}** effacés.", ephemeral=True)


@tree.command(name="clear", description="[Mod] Supprime des messages en masse")
@app_commands.describe(nombre="Nombre de messages à supprimer (1-100)")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, nombre: int):
    if not 1 <= nombre <= 100:
        await interaction.response.send_message("❌ Entre 1 et 100 messages.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=nombre)
    await interaction.followup.send(f"✅ {len(deleted)} message(s) supprimé(s).", ephemeral=True)
    await send_log(interaction.guild, make_embed(
        "🗑️ Purge de messages",
        f"**{len(deleted)}** messages supprimés dans {interaction.channel.mention} par {interaction.user.mention}",
        COLOR_WARNING
    ))


@tree.command(name="slowmode", description="[Mod] Active/désactive le slowmode")
@app_commands.describe(secondes="Délai en secondes (0 pour désactiver)")
@app_commands.checks.has_permissions(manage_channels=True)
async def slowmode(interaction: discord.Interaction, secondes: int):
    await interaction.channel.edit(slowmode_delay=secondes)
    if secondes == 0:
        await interaction.response.send_message("✅ Slowmode désactivé.")
    else:
        await interaction.response.send_message(f"✅ Slowmode activé : **{secondes}s**.")


@tree.command(name="lock", description="[Mod] Verrouille un salon")
@app_commands.checks.has_permissions(manage_channels=True)
async def lock(interaction: discord.Interaction):
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)
    await interaction.response.send_message("🔒 Salon verrouillé.")


@tree.command(name="unlock", description="[Mod] Déverrouille un salon")
@app_commands.checks.has_permissions(manage_channels=True)
async def unlock(interaction: discord.Interaction):
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=None)
    await interaction.response.send_message("🔓 Salon déverrouillé.")

# ══════════════════════════════════════════════════
#           COMMANDES UTILITAIRES / INFO
# ══════════════════════════════════════════════════

@tree.command(name="userinfo", description="Affiche les infos d'un membre")
@app_commands.describe(membre="Membre à inspecter")
async def userinfo(interaction: discord.Interaction, membre: discord.Member = None):
    m = membre or interaction.user
    roles = [r.mention for r in m.roles if r != interaction.guild.default_role]
    embed = discord.Embed(title=f"👤 Infos — {m}", color=m.color, timestamp=datetime.datetime.utcnow())
    embed.set_thumbnail(url=m.display_avatar.url)
    embed.add_field(name="ID", value=m.id, inline=True)
    embed.add_field(name="Pseudo", value=m.display_name, inline=True)
    embed.add_field(name="Bot ?", value="✅" if m.bot else "❌", inline=True)
    embed.add_field(name="Compte créé", value=m.created_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="A rejoint le", value=m.joined_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="Warnings", value=len(warnings.get(m.id, [])), inline=True)
    embed.add_field(name=f"Rôles ({len(roles)})", value=" ".join(roles[:10]) or "Aucun", inline=False)
    await interaction.response.send_message(embed=embed)


@tree.command(name="serverinfo", description="Affiche les infos du serveur")
async def serverinfo(interaction: discord.Interaction):
    g = interaction.guild
    embed = discord.Embed(title=f"🏠 {g.name}", color=COLOR_INFO, timestamp=datetime.datetime.utcnow())
    if g.icon:
        embed.set_thumbnail(url=g.icon.url)
    embed.add_field(name="ID", value=g.id, inline=True)
    embed.add_field(name="Propriétaire", value=g.owner.mention if g.owner else "?", inline=True)
    embed.add_field(name="Membres", value=g.member_count, inline=True)
    embed.add_field(name="Salons", value=len(g.channels), inline=True)
    embed.add_field(name="Rôles", value=len(g.roles), inline=True)
    embed.add_field(name="Boosts", value=g.premium_subscription_count, inline=True)
    embed.add_field(name="Créé le", value=g.created_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="Niveau vérif.", value=str(g.verification_level), inline=True)
    await interaction.response.send_message(embed=embed)


@tree.command(name="avatar", description="Affiche l'avatar d'un membre")
@app_commands.describe(membre="Membre dont afficher l'avatar")
async def avatar(interaction: discord.Interaction, membre: discord.Member = None):
    m = membre or interaction.user
    embed = discord.Embed(title=f"🖼️ Avatar de {m.display_name}", color=COLOR_INFO)
    embed.set_image(url=m.display_avatar.url)
    await interaction.response.send_message(embed=embed)


@tree.command(name="ping", description="Affiche la latence du bot")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    color = COLOR_SUCCESS if latency < 100 else (COLOR_WARNING if latency < 200 else COLOR_ERROR)
    await interaction.response.send_message(
        embed=make_embed("🏓 Pong !", f"Latence : **{latency}ms**", color)
    )


@tree.command(name="embed", description="[Mod] Envoie un message embed personnalisé")
@app_commands.describe(titre="Titre", contenu="Contenu", couleur="Couleur hex (ex: 3498DB)")
@app_commands.checks.has_permissions(manage_messages=True)
async def send_embed(interaction: discord.Interaction, titre: str, contenu: str, couleur: str = "3498DB"):
    try:
        color = int(couleur.replace("#", ""), 16)
    except:
        color = COLOR_INFO
    embed = discord.Embed(title=titre, description=contenu, color=color,
                          timestamp=datetime.datetime.utcnow())
    embed.set_footer(text=f"Envoyé par {interaction.user}")
    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("✅ Embed envoyé !", ephemeral=True)


@tree.command(name="sondage", description="Crée un sondage rapide 👍/👎")
@app_commands.describe(question="Question du sondage")
async def poll(interaction: discord.Interaction, question: str):
    embed = discord.Embed(title="📊 Sondage", description=question, color=COLOR_INFO,
                          timestamp=datetime.datetime.utcnow())
    embed.set_footer(text=f"Sondage par {interaction.user.display_name}")
    msg = await interaction.channel.send(embed=embed)
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")
    await interaction.response.send_message("✅ Sondage créé !", ephemeral=True)


@tree.command(name="aide", description="Affiche toutes les commandes disponibles")
async def aide(interaction: discord.Interaction):
    embed = discord.Embed(title="📖 Commandes du bot", color=COLOR_INFO,
                          timestamp=datetime.datetime.utcnow())
    embed.add_field(name="📋 Règlement", value="`/setup-reglement`", inline=False)
    embed.add_field(name="🎫 Tickets", value="`/setup-tickets`", inline=False)
    embed.add_field(name="🔨 Modération", value=(
        "`/kick` `/ban` `/unban`\n"
        "`/mute` `/unmute`\n"
        "`/warn` `/warnings` `/clearwarn`\n"
        "`/clear` `/slowmode` `/lock` `/unlock`"
    ), inline=False)
    embed.add_field(name="ℹ️ Informations", value="`/userinfo` `/serverinfo` `/avatar` `/ping`", inline=False)
    embed.add_field(name="🛠️ Utilitaires", value="`/embed` `/sondage`", inline=False)
    embed.add_field(name="🎵 TikTok Live", value="`/tiktok-add` `/tiktok-remove` `/tiktok-list`", inline=False)
    embed.set_footer(text="Bot Discord All-in-One")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ══════════════════════════════════════════════════
#           SURVEILLANCE LIVES TIKTOK
# ══════════════════════════════════════════════════

async def is_tiktok_live(username: str) -> bool:
    try:
        client = TikTokLiveClient(unique_id=username)
        is_live = await client.is_live()
        return is_live
    except UserOfflineError:
        return False
    except UserNotFoundError:
        print(f"[TikTok] Utilisateur @{username} introuvable.")
        return False
    except Exception as e:
        print(f"[TikTok] Erreur pour @{username} : {e}")
        return False


@tasks.loop(seconds=TIKTOK_CHECK_INTERVAL)
async def check_tiktok_lives():
    if not tiktok_users:
        return
    channel = bot.get_channel(TIKTOK_NOTIF_CHANNEL_ID)
    if channel is None:
        return
    for username in list(tiktok_users):
        live = await is_tiktok_live(username)
        if live and username not in tiktok_live_notified:
            tiktok_live_notified.add(username)
            embed = discord.Embed(
                title="🔴 Live TikTok en cours !",
                description=f"**@{username}** est en live sur TikTok ! Rejoins maintenant 👇",
                color=0xFF0050,
                url=f"https://www.tiktok.com/@{username}/live",
                timestamp=datetime.datetime.utcnow()
            )
            embed.set_footer(text="TikTok Live • Clique sur le titre pour rejoindre")
            await channel.send(embed=embed)
            print(f"[TikTok] Notif envoyée pour @{username}")
        elif not live and username in tiktok_live_notified:
            tiktok_live_notified.discard(username)
            print(f"[TikTok] Live terminé pour @{username}")


@check_tiktok_lives.before_loop
async def before_check():
    await bot.wait_until_ready()


@tree.command(name="tiktok-add", description="[Mod] Ajoute un compte TikTok à surveiller")
@app_commands.describe(username="Pseudo TikTok à surveiller (sans @)")
@app_commands.checks.has_permissions(manage_guild=True)
async def tiktok_add(interaction: discord.Interaction, username: str):
    username = username.lstrip("@")
    if username in tiktok_users:
        await interaction.response.send_message(f"⚠️ **@{username}** est déjà surveillé.", ephemeral=True)
        return
    tiktok_users.add(username)
    save_tiktok_users()
    await interaction.response.send_message(
        embed=make_embed("✅ TikTok ajouté", f"**@{username}** est maintenant surveillé.", COLOR_SUCCESS),
        ephemeral=True
    )


@tree.command(name="tiktok-remove", description="[Mod] Retire un compte TikTok de la surveillance")
@app_commands.describe(username="Pseudo TikTok à retirer (sans @)")
@app_commands.checks.has_permissions(manage_guild=True)
async def tiktok_remove(interaction: discord.Interaction, username: str):
    username = username.lstrip("@")
    if username not in tiktok_users:
        await interaction.response.send_message(f"❌ **@{username}** n'est pas dans la liste.", ephemeral=True)
        return
    tiktok_users.discard(username)
    tiktok_live_notified.discard(username)
    save_tiktok_users()
    await interaction.response.send_message(
        embed=make_embed("🗑️ TikTok retiré", f"**@{username}** ne sera plus surveillé.", COLOR_WARNING),
        ephemeral=True
    )


@tree.command(name="tiktok-list", description="Affiche les comptes TikTok surveillés")
async def tiktok_list(interaction: discord.Interaction):
    if not tiktok_users:
        await interaction.response.send_message("📋 Aucun compte TikTok surveillé pour l'instant.", ephemeral=True)
        return
    liste = "\n".join([
        f"{'🔴' if u in tiktok_live_notified else '⚫'} @{u}"
        for u in sorted(tiktok_users)
    ])
    embed = make_embed("📋 Comptes TikTok surveillés", liste, 0xFF0050)
    embed.set_footer(text="🔴 = en live actuellement • ⚫ = hors ligne")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ══════════════════════════════════════════════════

# ══════════════════════════════════════════════════

@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ Tu n'as pas les permissions requises.", ephemeral=True)
    elif isinstance(error, app_commands.BotMissingPermissions):
        await interaction.response.send_message("❌ Je n'ai pas les permissions nécessaires.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Une erreur est survenue : {error}", ephemeral=True)
        print(f"Erreur commande : {error}")

# ══════════════════════════════════════════════════
#                   LANCEMENT
# ══════════════════════════════════════════════════

if __name__ == "__main__":
    bot.run(TOKEN)