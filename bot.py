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
    def __init__(self, challenger_user, defender_user):

        self.challenger = challenger_user
        self.defender = defender_user

        self.id = create_duel_id(int(self.challenger.id), int(self.defender.id))

        self.add_duel()

    def add_duel(self):
        global mycursor
        global mydb

        query = '''INSERT INTO duel (duel_id, challenger_id, defender_id, created_at)
                VALUES ('%s', '%s', '%s', '%s')
                ''' % (
                    self.id, 
                    self.challenger.id, 
                    self.defender.id, 
                    self.get_datetime()
                )

        mycursor.execute(query)

        mydb.commit()


    #   adds fifteen minutes to the creation-time and stores it
    #   Defender has to accept duel by this time or the duel is
    #   automatically cancelled._
    def acceptance_time_limit(self, time):
        return str(str(time)[:3] + str(int(str(time)[3:]) + 15))

    def get_datetime(self):
        now = datetime.datetime.now()
        return now

    def store_channel(self, channel):
        self.channel_ = channel

    # async def accepted_duel(self):

    async def duel_response(self, indicator, response_index):
        self.cancelled = not int(indicator)

        self.accepted = int(indicator)

        if not self.accepted:
            await cancel_duel(self, response_index)

        else:
            global duel_clocks_list
            self.duel_clock_index = duel_clocks_list[self.duel_clock_index].duel_accepted(self.duel_clock_index)


        self.response_time = self.get_time()

        self.time_limit = str(int(self.response_time[:2]) + 2) + self.response_time[2:]

        sheet = open_sheets(0)

        sheet.update_cell(self.row, 12, self.time_limit)

        sheet = open_sheets(0)

        sheet.update_cell(self.row, 9, self.accepted)
        sheet.update_cell(self.row, 10, self.response_time)

    def limit_reach(self):

        self.cancelled = True

        self.winning_time = "N/A"
        self.winner = "N/A"

        sheet = open_sheets(0)

        sheet.update_cell(self.row, 11, '*')
        sheet.update_cell(self.row, 13, self.winning_time)
        sheet.update_cell(self.row, 14, self.winner)

    def set_winner(self, winner):
        if self.cancelled:
            print('This duel has been cancelled')   
            return

        self.winning_time = self.get_time()
        self.winner = winner

        sheet = open_sheets(0)

        sheet.update_cell(self.row, 13, self.winning_time)
        sheet.update_cell(self.row, 14, self.winner.name)
        
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
DUELS_CAT = os.getenv('DUELS_CATEGORY_ID')
MOD_CHANNEL_ID = os.getenv('MOD_CHANNEL_ID')
DIRECTORY_ = os.getenv('DIRECTORY')

client = discord.Client()

DB_USERNAME = os.getenv('USERNAME')
DB_PASSWORD = os.getenv('PASSWORD')
DB_DATABASE = os.getenv('DATABASE')

mydb = mysql.connector.connect(
    host = 'localhost',
    user = 'testuser',
    password = DB_PASSWORD,
    database= DB_DATABASE
)

mycursor = mydb.cursor()


cancellation_reasons = {    #   dictionary for  index -> duel-cancellation reasons
                        0: 'The Defender has rejected the duel.', 
                        1: 'The Challenger has cancelled the duel.',        
                        2: 'The Defender has failed to respond to the duel in time.',
                        3: 'The Duel was not completed within the two hour window.'
                    }

duel_id_list = []  #   dictionary for duel_id -> Duel()

# pending_duel_clocks = []
duel_clocks_list = []

@client.event
async def on_ready():
    global duel_id_list

    worksheet_names = {0: 'Table'}

    print(f'{client.user} has connected to Discord')
    duel_id_list = retrieve_duel_id_list()

@client.event
async def on_message(message):

    if message.author == client.user:
        return

    if (message.content == "hello"):
        response = "'ello 'ello 'ello. You got a loicense for that gree'ing mate?"

        await message.channel.send(response)
    
    elif message.content == '!signup':
        
        if not check_signed_up(message.author.id):
            add_user(message.author)
            response = "Profile created. You can now participate in the Duelling system."
            await message.channel.send(response)
            return

        response = "You are already signed up."
        await message.channel.send(response)

    elif '!duel' in message.content:

        challenger = message.author

        if not check_signed_up(challenger.id):
            add_user(challenger)
            response = "No profile found in database. New profile has been made for {}."
            response = response.format(challenger.mention)
            await message.channel.send(response)

        defender = message.mentions[0]

        if not check_signed_up(defender.id):
            add_user(defender)
            response = "No profile found in database. New profile has been made for {}."
            response = response.format(defender.mention)
            await message.channel.send(response)

        new_duel = Duel(challenger, defender)

        if create_duel(new_duel):
            await create_duel_channel(message, new_duel)
            # initial_sheet_fill(new_duel)

    elif message.channel.category_id == int(DUELS_CAT):
        
        content = message.content
        id_ = int(message.channel.topic[:4])

        if content == '!accept':
            await respond_duel(id_, message.author.id, True, None, message.channel)

        elif content == '!reject':
            await respond_duel(id_, message.author.id, False, 0, message.channel)

        elif content == '!cancel' and current_duel.accepted == -1 and message.author.name == current_duel.challenger.name:
            await respond_duel(id_, message.author.name, False, 1, message.channel)

        elif '!dispute' in content:
            await send_dispute(content.split(" ", 1)[1], message.channel)

        elif '!winner' in content:
            await declare_winner(id_, message.mentions[0], message.channel)

    elif message.content == '!reset':
        await reset_channels(message.guild)

        await message.channel.send('Duels have been reset')

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

#   confirms the duel and its legality and if legal:
#       adds the duel to the dictionary
def create_duel(duel_):

    id_ = duel_.id
    offset = 0

    while check_duel_id_exists(id_) == False:
        offset = random.randint(1, 50)
        id_ += offset

    if check_if_allowed(duel_.challenger.id):
        id_ = check_duel_id(id_)

        duel_list[id_] = duel_

        return True
    else:
        return False

#   checks whether the challenger has already created a challenge
#   or if they have an already out-standing challenge waiting
#   i.e. multiple people can challenge one person, but one person 
#   cannot create a challenge before responding to the ones they
#   have already been provided with
def check_if_allowed(challenger_id):
    global mycursor

    query_options = {
                        0 : "challenger_id",
                        1 : "defender_id"
                }

    x = 0
    while x <= 1:
        active_option = query_options[x]

        query = "SELECT '%s', ended_at FROM duel WHERE '%s' = '%s'" % (
            active_option, active_option, challenger_id)

        mycursor.execute(query)

        results = mycursor.fetchall()

        if int(results[0]) == int(challenger_id):
            print("Hello hello")
            return False

        x += 1

    return True

#   if the duel_id already exists within the dictionary
#   recursively creates a new one
def check_duel_id_exists(duel_id):
    global duel_id_list

    return duel_id in duel_id_list

def get_firelord(guild_):
    return guild_.roles[len(guild_.roles) - 1]

def get_at_everyone(guild_):
    return guild_.default_role

#   creates the channel for a given duel
async def create_duel_channel(message, duel_):

    challenger = duel_.challenger
    defender = duel_.defender
    id_ = duel_.id
    guild_ = message.guild

    duel_channel_name = (challenger.name + ' vs ' + defender.name).lower()

    firelord_role = get_firelord(guild_)    # get highest role
    at_everyone = get_at_everyone(guild_)

    #   apply permits for the channel, where:
    #       -   Moderators get to do whatever they wish
    #       -   Challenger and Defender get to send & read messages
    #       -   @everyone only gets to see messages
    overwrites = {
        firelord_role : discord.PermissionOverwrite(read_messages = True, send_messages = True),

        challenger: discord.PermissionOverwrite(read_messages = True, send_messages = True),
        
        defender: discord.PermissionOverwrite(read_messages = True, send_messages = True),

        at_everyone : discord.PermissionOverwrite(read_messages = True, send_messages = False)
    }

    #   create the duel-channel for the two participants under the Duels category
    await guild_.create_text_channel(duel_channel_name, overwrites=overwrites, 
        category=discord.utils.get(guild_.categories, id=int(DUELS_CAT)), topic=str(id_))

    duel_channel = discord.utils.get(guild_.text_channels, topic=str(id_))

    duel_.store_channel(duel_channel)

    response = 'New challenge created with ID: ' + str(id_) + "\n Head over to {} for more details."
    response = response.format(duel_channel.mention)

    await message.channel.send(response)

    response = '{} has been challenged by {} \n Please type !accept or !reject in accordance to what you wish to do with this challenge.'
    response = response.format(defender.mention, challenger.mention)
    await duel_channel.send(response)

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
async def respond_duel(id_, responder_id, response, message_indicator, channel):
    
    current_duel = retrieve_duel(id_)

    responder_id_c = int(responder_id)

    if current_duel[4] != None:
        response = 'Duel has already been responded to. '
        return

    if responder_id_c == int(current_duel[2]):
        if response:
            await true_response(channel, id_)
        else:
            await false_response(channel, id_)

    elif responder_id_c == int(current_duel[1]):
        response = '''Please allow the **Defender** to !confirm or !reject the Duel\nIf you, as the **Challenger**, no longer wish to Duel, then please indicate so by typing !cancel'''
        await channel.send(response)
    else:
        response = 'You are not a participant of the Duel'
        await channel.send(response)

async def true_response(channel, id_):
    global mycursor
    global mydb

    query = "UPDATE duel SET accepted = '{}', accepted_at = '{}' WHERE duel_id = '{}'"
    query = query.format(1, datetime.datetime.now(), id_)

    mycursor.execute(query)
    mydb.commit()

    response = 'The Duel has been accepted! \n You now have **TWO** hours to complete the Duel! \n Good luck to both and make sure to have fun!'
    await channel.send(response)

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

    mod_channel = await client.fetch_channel(int(MOD_CHANNEL_ID))
    firelord_role =  channel.guild.roles[len(channel.guild.roles) - 1]  #   Firelord is the highest rank in the server
       
    response = '{}\nDuel ' + channel.topic[:4] + ' has been disputed with the following reason: \n> ' + reason + ' \n \nChannel link: {}'
    response = response.format(firelord_role.mention, channel.mention)

    await mod_channel.send(response)

    response = "A Dispute-request has been sent to the Firelord's. One will be with you as soon as possible."
    await channel.send(response)

async def declare_winner(id_, winner, channel):
    
    current_duel = retrieve_duel(id_)

    current_duel.set_winner(winner)

    await channel.edit(topic=str(id_) + " WINNER: " + winner.name)

    response = 'The winner of Duel ' + str(id_) + ' is: **' + winner.name + '** !\n 🥳🎉 **Congratulations!** 🥳🎉'
    await channel.send(response)

def create_duel_clock(duel, time):
    new_timer = Duel_Clock(duel, time, 2)
    duel_clocks_list.append(new_timer)
    return (len(duel_clocks_list) - 1) #    returns the length of the list, as the position of the new clock is at the back

async def cancel_duel(id_, channel, reason_index):

    guild_reference = channel.guild

    duel_participants = retrieve_participants(id_)

    at_everyone = get_at_everyone(guild_reference)
    firelord_role = get_firelord(guild_reference)
    challenger = await client.fetch_user(int(duel_participants[0]))
    defender = await client.fetch_user(int(duel_participants[1]))

    overwrites = {
        firelord_role : discord.PermissionOverwrite(read_messages = True, send_messages = True),

        challenger: discord.PermissionOverwrite(read_messages = True, send_messages = False),
        
        defender: discord.PermissionOverwrite(read_messages = True, send_messages = False),

        at_everyone : discord.PermissionOverwrite(read_messages = True, send_messages = False)
    }

    await channel.edit(overwrites=overwrites)

    await channel.send('This duel has been cancelled for the following reason: \n> ' + cancellation_reasons[reason_index] + 
                                ' \nBoth participants will be sent a private message with a confirmation \n \n**This channel will be deleted in a moment.**')

    response = 'Your duel with **{}** was cancelled for the following reason: \n> ' + cancellation_reasons[reason_index]
    response = response.format(defender.name)

    private_channel = await challenger.create_dm()
    await private_channel.send(response)

    response = 'Your duel with **{}** was cancelled for the following reason: \n> ' + cancellation_reasons[reason_index]
    response = response.format(challenger.name)

    private_channel = await defender.create_dm()
    await private_channel.send(response)

def retrieve_duel(id_):
    global mycursor

    query = "SELECT * FROM duel WHERE duel_id = '%s'" % (id_)

    mycursor.execute(query)

    myresult = mycursor.fetchall()

    return myresult[0]

def retrieve_participants(id_):
    global mycursor
    
    query = "SELECT challenger_id, defender_id FROM duel WHERE duel_id = '%s'" % (id_)

    mycursor.execute(query)

    participants = mycursor.fetchall()

    return participants[0]

def retrieve_duel_id_list():
    global mycursor

    query = "SELECT duel_id FROM duel"

    mycursor.execute(query)

    return mycursor.fetchall()

client.run(TOKEN)