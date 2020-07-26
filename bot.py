#   bot.py

import os
import random
import sys
import datetime
import time
import asyncio
import mysql.connector

import discord
from dotenv import load_dotenv

class Duel():
    def __init__(self, duel_id, challenger_user, defender_user, accepted_):

        self.id_ = duel_id
        self.challenger = challenger_user
        self.defender = defender_user
        self.accepted = accepted_

    #   upon creating a new duel, its details are added to the database
    def add_duel(self):
        global mycursor
        global mydb

        query = '''INSERT INTO duel (duel_id, challenger_id, defender_id, created_at)
                VALUES ('%s', '%s', '%s', '%s')
                ''' % (
                    self.id_, 
                    self.challenger.id, 
                    self.defender.id, 
                    self.get_datetime()
                )

        mycursor.execute(query)

        mydb.commit()


    #   adds fifteen minutes to the creation-time and stores it
    #   Defender has to accept duel by this time or the duel is
    #   automatically cancelled.

    # def acceptance_time_limit(self, time):
    #     return str(str(time)[:3] + str(int(str(time)[3:]) + 15))

    def get_datetime(self):
        return datetime.datetime.now()

    #   upon creating a text-channel for a duel, a reference to its ID is stored
    def store_channel(self, channel):
        self.channel_id = channel.id

    # async def accepted_duel(self):

    async def duel_response(self, indicator, response_index):
        self.cancelled = not int(indicator)

        self.accepted = int(indicator)

        if not self.accepted:
            await cancel_duel(self, response_index)

    def set_winner(self, challenger_wins):
        global mycursor
        global mydb

        query = "UPDATE duel SET ended_at = '{}', winner_id = '{}' WHERE duel_id = {}"
        query = query.format(self.get_datetime(), self.challenger.id if challenger_wins else self.defender.id, self.id_)
        mycursor.execute(query)
        mydb.commit()

        query = "UPDATE user SET wins = wins + 1 WHERE user_id = '%s'"
        query = query % (self.challenger.id if challenger_wins else self.defender.id)
        mycursor.execute(query)
        mydb.commit()

        query = "UPDATE user SET losses = losses + 1 WHERE user_id = '%s'"
        #   changed this (query) to be other way around for the sake of readability
        query = query % (self.defender.id if challenger_wins else self.challenger.id)
        mycursor.execute(query)
        mydb.commit()
        
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
DUELS_CAT = os.getenv('DUELS_CATEGORY_ID')
MOD_CHANNEL_ID = os.getenv('MOD_CHANNEL_ID')
DIRECTORY_ = os.getenv('DIRECTORY')

client = discord.Client()

DB_USERNAME = os.getenv('USERNAME')
DB_PASSWORD = os.getenv('PASSWORD')
DB_DATABASE = os.getenv('DATABASE')

RESET_PASSWORD = os.getenv('RESET_PASSWORD')

colour_code = 0xF68329

mydb = mysql.connector.connect(
    host = 'localhost',
    user = 'testuser',
    password = DB_PASSWORD,
    database= DB_DATABASE
)
mycursor = mydb.cursor()

cancellation_reasons = {    #   dictionary for  index -> duel-cancellation reason
                        0: 'The Defender has rejected the duel.', 
                        1: 'The Challenger has cancelled the duel.',        
                        2: 'The Defender has failed to respond to the duel in time.',
                        3: 'The Duel was not completed within the two hour window.'
                    }

duel_dictionary = {}  #   dictionary for duel_id -> Duel()
pending_delete = {} #dictionary for duel_id -> Duel-to-be-deleted

@client.event
async def on_ready():
    global duel_dictionary

    print(f'{client.user} has connected to Discord')
    await fill_duel_dictinary()


@client.event
async def on_message(message):

    if message.author == client.user:
        return

    if (message.content == "hello"):
        response = discord.Embed(title="'ello 'ello 'ello. You got a loicense for that gree'ing mate?")
        await message.channel.send(embed=response)
    
    elif message.content == '!signup':
        
        if not check_signed_up(message.author.id):
            add_user(message.author)
            response = discord.Embed(description="Profile created. You can now participate in the Duelling system.", 
                                    color=colour_code)
            await message.channel.send(embed=response)
            return

        response = discord.Embed(title="You are already signed up.", 
                                color=colour_code)
        await message.channel.send(embed=response)

    elif '!duel' in message.content:

        if len(message.mentions) == 0:
            response = "Please @-mention the person you wish to duel"
            await message.channel.send(response)
            return

        challenger = message.author

        if not check_signed_up(challenger.id):
            add_user(challenger)
            response = discord.Embed(title="No profile found in database.", 
                                    description="New profile has been made for {}.", 
                                    color=colour_code)
            response = response.format(challenger.mention)
            await message.channel.send(response)

        defender = message.mentions[0]

        if not check_signed_up(defender.id):
            add_user(defender)
            response = discord.Embed(title="No profile found in database.", 
                                    description="New profile has been made for {}.", 
                                    color=colour_code)
            response = response.format(defender.mention)
            await message.channel.send(response)

        duel_id = create_duel_id(challenger.id, defender.id)

        duel_id = pre_duel_creation(duel_id, challenger.id)

        global duel_dictionary

        if duel_id != -1:
            new_duel = Duel(duel_id, challenger, defender, False)
            duel_dictionary[duel_id] = new_duel

            new_duel.add_duel()

            await create_duel_channel(message, new_duel)
        
        else:
            response = "You already have outstanding duels. Please respond to them before creating a new one."

    elif message.channel.category_id == int(DUELS_CAT):
        
        content = message.content
        id_ = int(message.channel.topic[:4])

        if content == '!accept':
            await respond_duel(id_, message.author.id, True, message.channel)

        elif content == '!reject':
            await respond_duel(id_, message.author.id, False, message.channel)

        # elif content == '!cancel' and current_duel.accepted == -1 and message.author.name == current_duel.challenger.name:
        #     await respond_duel(id_, message.author.name, False, 1, message.channel)

        elif '!dispute' in content:
            dispute_reason = "No reason given"

            split = content.split(" ", 1)
            if len(split) > 1: #    if a reason has been given, the string is changed to that
                dispute_reason = split[1]

            await send_dispute(dispute_reason, message.channel)

        elif '!winner' in content:
            if len(message.mentions) == 0:
                response = "Please @-mention the winner of the duel"
                await message.channel.send(response)
                return

            await declare_winner(id_, message.mentions[0], message.channel)

    elif '!reset' in message.content:
        if check_for_reset(message):
            await message.channel.send("vibe")
        else:
            await message.channel.send("not vibe")

        await message.delete()

        # await reset_channels(message.guild)

        # await message.channel.send('Duels have been reset')

    elif '!stats' in message.content:
        if len(message.mentions) <= 0:
            await retrieve_player_stats(message.author.id, message.channel)
        else:
            await retrieve_player_stats(message.mentions[0], message.channel)



def check_signed_up(challenger_id):
    sql = "SELECT user_id FROM user WHERE user_id = '%s'" % (challenger_id)

    mycursor.execute(sql)

    myresult = mycursor.fetchall()

    return len(myresult) > 0

def add_user(challenger):
    global mycursor
    global mydb

    query = '''INSERT INTO user (user_id, user_name, joindate, wins, losses, self_cancels, cancels, disputes) 
        VALUES ('%s', '%s', '%s', 0, 0, 0, 0, 0)
        ''' % (
            challenger.id, 
            challenger.name, 
            datetime.datetime.now()
        )

    mycursor.execute(query)

    mydb.commit()

def check_for_reset(message):

    firelord_role = get_firelord(message.guild)

    split = message.content.split( )
    print(split)

    if firelord_role.name.lower() not in [y.name.lower() for y in message.author.roles]:
        print("role")
        return False

    print(len(split))

    if len(split) != 2: 
        print("len")
        return False

    if split[1].lower() != RESET_PASSWORD:
        print("pw")
        return False

    return True

#   confirms the duel and its legality and if legal:
#       adds the duel to the dictionary
def pre_duel_creation(id_, challenger_id):
    offset = 0

    while check_duel_id_exists(id_) != False:
        offset = random.randint(1, 50)
        id_ += offset

    if check_if_allowed(challenger_id):
        return id_
    else:
        return -1

#   checks whether the challenger has already created a challenge
#   or if they have an already out-standing challenge waiting
#   i.e. multiple people can challenge one person, but one person 
#   cannot create a challenge before responding to the ones they
#   have already been provided with
def check_if_allowed(challenger_id):
    global mycursor
        
    active_duels = []

    query = "SELECT duel_id FROM duel WHERE challenger_id = '%s' AND ended_at IS NULL" % (challenger_id)
    mycursor.execute(query)
    results = mycursor.fetchall()

    active_duels.extend(results)

    query = "SELECT duel_id FROM duel WHERE defender_id = '%s' AND ended_at IS NULL" % (challenger_id)
    mycursor.execute(query)
    results = mycursor.fetchall()

    active_duels.extend(results)

    return not (len(active_duels) > 0)


#   if the duel_id already exists within the dictionary
#   recursively creates a new one
def check_duel_id_exists(duel_id):
    global mycursor

    query = "SELECT duel_id FROM duel"

    mycursor.execute(query)

    duel_ids = mycursor.fetchall()

    for id_ in duel_ids:
        if int(duel_id) == int(id_[0]):
            return True
        
    return False

def get_firelord(guild_):
    return guild_.roles[len(guild_.roles) - 1]

def get_at_everyone(guild_):
    return guild_.default_role

#   creates the channel for a given duel
async def create_duel_channel(message_, duel_):

    guild_ = message_.guild

    id_ = duel_.id_
    challenger = duel_.challenger
    defender = duel_.defender
    firelord_role = get_firelord(message_.guild)
    at_everyone_role = get_at_everyone(message_.guild)

    duel_channel_name = (challenger.name + ' vs ' + defender.name).lower()

    #   apply permits for the channel, where:
    #       -   Moderators get to do whatever they wish
    #       -   Challenger and Defender get to send & read messages
    #       -   @everyone only gets to see messages
    overwrites = {
        firelord_role : discord.PermissionOverwrite(read_messages = True, send_messages = True),

        challenger: discord.PermissionOverwrite(read_messages = True, send_messages = True),
        
        defender: discord.PermissionOverwrite(read_messages = True, send_messages = True),

        at_everyone_role : discord.PermissionOverwrite(read_messages = True, send_messages = False)
    }

    #   create the duel-channel for the two participants under the Duels category
    await guild_.create_text_channel(duel_channel_name, overwrites=overwrites, 
        category=discord.utils.get(guild_.categories, id=int(DUELS_CAT)), topic=str(id_))

    duel_channel = discord.utils.get(guild_.text_channels, topic=str(id_))

    duel_.store_channel(duel_channel)

    response = discord.Embed(title='New Duel created',
                            description='Head over to %s for more details.' % duel_channel.mention,
                            color=colour_code)
    
    response.set_author(name="Duel ID: " + str(id_))

    await message_.channel.send(embed=response)

    response = discord.Embed(title='%s has been challenged by %s' % (defender.name, challenger.name), 
                            description='Please type !accept or !reject in accordance to what you wish to do with this challenge.',
                            color=colour_code)
    await duel_channel.send(embed=response)

#   deletes all the channels under Duels-category
async def reset_channels(guild_):
    category = discord.utils.get(guild_.categories, id=int(DUELS_CAT))

    for channels in category.channels:
        await channels.delete()

async def delete_channel(channel):
    await channel.delete()

#   duel_id is obtained by taking the last four digits of the result of
#   adding the two players' ID's together and dividing this by two
def create_duel_id(challenger_id, defender_id):
    duel_id = int((challenger_id + defender_id) / 2)
    duel_id = int(str(duel_id)[-4:])

    return int(duel_id)

#   takes the response of defender
async def respond_duel(id_, responder_id, response, channel):
    
    current_duel = retrieve_duel(id_)

    # if current_duel[4] != None:
    #     response = 'Duel has already been responded to.'
    #     return

    #   if the id of the responder matches that of the defender
    if int(responder_id) == int(current_duel.defender.id):

        await true_response(channel, id_) if response else await false_response(channel, id_)
        
    #   if the id of the responder matches that of the challenger
    elif int(responder_id) == int(current_duel.challenger.id):
        response = discord.Embed(title='Please allow the Defender to !confirm or !reject the duel',
                                description='If you, as the **Challenger**, no longer wish to duel, then please indicate so by typing **!cancel**',
                                color=colour_code)

        await channel.send(embed=response)
    
    #   else
    else:
        response = discord.Embed(title='You are not a participant of the Duel')
        await channel.send(embed=response)

async def true_response(channel, id_):
    global mycursor
    global mydb

    query = "UPDATE duel SET accepted = '{}', accepted_at = '{}' WHERE duel_id = '{}'"
    query = query.format(1, datetime.datetime.now(), id_)

    mycursor.execute(query)
    mydb.commit()

    response = discord.Embed(title='The duel has been accepted',
                            description='You have **TWO** hours to complete the duel',
                            color=0x38E935)
    response.add_field(name='Good luck to both!', 
                      value="Type **!help** for help with commands")
    await channel.send(embed=response)

async def false_response(channel, id_):
    global mycursor
    global mydb
    
    query = "UPDATE duel SET accepted  = '{}', ended_at = '{}' WHERE duel_id = '{}'"
    query = query.format(0, datetime.datetime.now(), id_)

    mycursor.execute(query)
    mydb.commit()

    await cancel_duel(id_, channel, 0)

    await asyncio.sleep(10)
    await delete_channel(channel)

async def send_dispute(reason, channel):
    global firelord_role

    mod_channel = await client.fetch_channel(int(MOD_CHANNEL_ID))
       
    response = '{}\nDuel ' + channel.topic[:4] + ' has been disputed with the following reason: \n> ' + reason + ' \n \nChannel link: {}'
    response = response.format(firelord_role.mention, channel.mention)

    await mod_channel.send(response)

    response = "A Dispute-request has been sent to the Firelord's. One will be with you as soon as possible."
    await channel.send(response)

async def declare_winner(id_, winner, channel):
    
    current_duel = retrieve_duel(id_)

    indicator = False
    if winner.id == current_duel.challenger.id:
        indicator = True

    current_duel.set_winner(winner)

    await channel.edit(topic=str(id_) + " WINNER: " + winner.name)

    response = ('The winner of Duel ' + str(id_) + ' is: **' + winner.name + '** !\n 🥳🎉 **Congratulations!** 🥳🎉\n This channel will be deleted in **5 minutes**. If you wish to dispute the duel, please indicate so by typing **!dispute**')
    await channel.send(response)

def create_duel_clock(duel, time):
    new_timer = Duel_Clock(duel, time, 2)
    duel_clocks_list.append(new_timer)
    return (len(duel_clocks_list) - 1) #    returns the length of the list, as the position of the new clock is at the back

async def cancel_duel(id_, channel, reason_index):
    global firelord_role
    global at_everyone_role

    guild_reference = channel.guild

    duel_participants = retrieve_participants(id_)

    firelord_role = get_firelord(guild_reference)
    at_everyone_role = get_at_everyone(guild_reference)
    challenger = await client.fetch_user(int(duel_participants[0]))
    defender = await client.fetch_user(int(duel_participants[1]))

    overwrites = {
        firelord_role : discord.PermissionOverwrite(read_messages = True, send_messages = True),

        challenger: discord.PermissionOverwrite(read_messages = True, send_messages = False),
        
        defender: discord.PermissionOverwrite(read_messages = True, send_messages = False),

        at_everyone_role : discord.PermissionOverwrite(read_messages = True, send_messages = False)
    }

    await channel.edit(overwrites=overwrites)

    response = discord.Embed(title='This duel has been cancelled for the following reason:',
                            description=cancellation_reasons[reason_index],
                            color=0xE73D3D)
    response.add_field(name="Both participants will be sent a private message with a confirmation",
                      value='**This channel will be deleted in a moment.**')
    await channel.send(embed=response)


    response = discord.Embed(title='Your duel with **%s** was cancelled for the following reason:' % challenger.name,
                            description=cancellation_reasons[reason_index],
                            color=colour_code)
    response = 'Your duel with **{}** was cancelled for the following reason: \n> ' + cancellation_reasons[reason_index]

    private_channel = await challenger.create_dm()
    await private_channel.send(response)

    response = discord.Embed(title='Your duel with **%s** was cancelled for the following reason:' % defender.name,
                            description=cancellation_reasons[reason_index],
                            color=colour_code)
    response = 'Your duel with **{}** was cancelled for the following reason: \n> ' + cancellation_reasons[reason_index]

    private_channel = await defender.create_dm()
    await private_channel.send(response)

def retrieve_duel(id_):
    global duel_dictionary

    return duel_dictionary[id_]

def retrieve_participants(id_):
    global mycursor
    
    query = "SELECT challenger_id, defender_id FROM duel WHERE duel_id = '%s'" % (id_)

    mycursor.execute(query)

    participants = mycursor.fetchall()

    return participants[0]

#   upon activating the bot, fills duel_dictionary with currently active duels
async def fill_duel_dictinary():
    global mycursor
    global duel_dictionary

    query = "SELECT duel_id, challenger_id, defender_id, accepted FROM duel WHERE ended_at IS NULL"

    mycursor.execute(query)

    active_duels = mycursor.fetchall()

    for duel in active_duels:
        challenger = await client.fetch_user(int(duel[1]))
        defender = await client.fetch_user(int(duel[2]))

        duel_instance = Duel(duel[0], challenger, defender, False if duel[3] == "None" else True)
        duel_dictionary[duel[0]] = duel_instance

async def retrieve_player_stats(user_id, channel):
    global mycursor

    embed_message = discord.Embed(title="Title", description="description", color=colour_code)

    await channel.send(embed=embed_message)

    # query = "SELECT wins, losses FROM user WHERE user_id = '%s'" % (user_id)
    # mycursor.execute(query)

    # stats = mycursor.fetchall()
client.run(TOKEN)