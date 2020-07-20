#   bot.py

import os
import random
import sys
from datetime import datetime
import time
import asyncio

import discord
from dotenv import load_dotenv

import gspread
from oauth2client.service_account import ServiceAccountCredentials

class Duel():
    def __init__(self, challenger_user, defender_user):
        global row_index

        self.id = create_duel_id(int(challenger_user.id), int(defender_user.id))
        self.challenger = challenger_user
        self.defender = defender_user
        self.time = self.get_time()
        self.row = row_index

        self.accepted = -1
        self.acceptance_limit = self.acceptance_time_limit(self.time)

        self.duel_clock_index = create_duel_clock(self, 30) #   make this 15 minutes

        self.cancelled = False

    def __del__(self):
        print("Duel " + self.id + " has been deleted")

    #   adds fifteen minutes to the creation-time and stores it
    #   Defender has to accept duel by this time or the duel is
    #   automatically cancelled._
    def acceptance_time_limit(self, time):
        return str(str(time)[:3] + str(int(str(time)[3:]) + 15))

    def get_time(self):
        return str(datetime.now().time())[:5]

    def store_channel(self, channel):
        self.channel_ = channel

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
        
#   Place Duel_Clock
class Duel_Clock():
    def __init__(self, duel, time, index):
        self.duel = duel
        self.time_ = time
        self.type = index

    def __del__(self):
        print(self.duel.id + " Duel Clock being deleted")

    def timeout(self):
        self.duel.limit_reach()

    def duel_accepted(self, position):
        self.time = 60
        self.index = 3
        
        global duel_clocks_list

        duel_clocks_list.append(duel_clocks_list.pop(position))

        return len(duel_clocks_list) - 1
        # active_duel_clocks.append(pending_duel_clocks.pop(self))

load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
DUELS_CAT = os.getenv('DUELS_CATEGORY_ID')
MOD_CHANNEL_ID = os.getenv('MOD_CHANNEL_ID')
DIRECTORY_ = os.getenv('DIRECTORY')

client = discord.Client()

row_index = 2

worksheet_names = { #  dictionary for index -> name
                    0: 'Table'
                } 

cancellation_reasons = {    #   dictionary for  index -> duel-cancellation reasons
                        0: 'The Defender has rejected the duel.', 
                        1: 'The Challenger has cancelled the duel.',        
                        2: 'The Defender has failed to respond to the duel in time.',
                        3: 'The Duel was not completed within the two hour window.'
                    }

duel_list = {}  #   dictionary for duel_id -> Duel()

# pending_duel_clocks = []
duel_clocks_list = []

channels_pending_deletion = []
duels_pending_deletion = []

@client.event
async def on_ready():
    global worksheet_names

    worksheet_names = {0: 'Table'}

    print(f'{client.user} has connected to Discord') 

@client.event
async def on_message(message):

    if message.author == client.user:
        return

    if (message.content == "hello"):
        response = "'ello 'ello 'ello. You got a loicense for that gree'ing mate?"

        await message.channel.send(response)
    
    elif '!duel' in message.content:

        challenger = message.author
        defender = message.mentions[0]

        new_duel = Duel(challenger, defender)

        if create_duel(new_duel):
            await create_duel_channel(message, new_duel)
            initial_sheet_fill(new_duel)

    elif message.channel.category_id == int(DUELS_CAT):
        
        content = message.content
        id_ = int(message.channel.topic[:4])
        current_duel = retrieve_duel(int(id_))

        if content == '!accept' and current_duel.accepted == -1:
            await respond_duel(id_, message.author.name, True, None, message.channel)

        elif content == '!reject' and current_duel.accepted == -1:
            await respond_duel(id_, message.author.name, False, 0, message.channel)

        elif content == '!cancel' and current_duel.accepted == -1 and message.author.name == current_duel.challenger.name:
            await respond_duel(id_, message.author.name, False, 1, message.channel)

        elif '!dispute' in content:
            await send_dispute(content.split(" ", 1)[1], message.channel)

        elif '!winner' in content:
            await declare_winner(id_, message.mentions[0], message.channel)

    elif message.content == '!reset':
        # global pending_duel_clocks
        global duel_clocks_list

        reset_sheets()

        await reset_channels(message.guild)

        # pending_duel_clocks = []
        duel_clocks_list = []

        await message.channel.send('Duels have been reset')

#   confirms the duel and its legality and if legal:
#       adds the duel to the dictionary
def create_duel(duel_):
    global duel_list

    id_ = duel_.id

    if (check_if_allowed(duel_)):
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
def check_if_allowed(duel_):
   
    global duel_list

    d_items = duel_list.items()

    for key, value in d_items:
        if value.challenger == duel_.challenger.name:
            return False
        
        if value.defender == duel_.challenger.name:
            return False

    return True

#   if the duel_id already exists within the dictionary
#   recursively creates a new one
def check_duel_id(duel_id):
   
    global duel_list

    adjusted_id = duel_id

    d_items = duel_list.items()

    for key, value in d_items:
        
        if key == duel_id:
            new_id = duel_id + random.randint(20, 50)
            adjusted_id = check_duel_id(duel_list, new_id)

    return adjusted_id

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

    firelord_role = get_firelord(guild_)    #    get highest role
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

#   taps into the gspread API and returns the needed worksheet
def open_sheets(sheet_index):
    dir = DIRECTORY_

    scope = ['https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(dir, scope)
    client = gspread.authorize(creds)

    worksheet = client.open('Duel Database').worksheet(get_sheet_name(sheet_index))

    return worksheet

#   deletes all entries in the data-table (barring titles)
def reset_sheets():
    global row_index

    sheet = open_sheets(0)

    sheet.delete_rows(2, row_index)

    row_index = 2

#   deletes all the channels under Duels-category
async def reset_channels(guild_):
    category = discord.utils.get(guild_.categories, id=int(DUELS_CAT))

    for channels in category.channels:
        await channels.delete()

async def delete_channel(channel):
    await channel.delete()

#   returns the name of the sheet for a given index, where
#   the name is obtained from the worksheet_names dictionary
def get_sheet_name(index):
    return worksheet_names[index]

#   fills the google-sheets database with the initial duel information
#   these being:
#   duel-id, creation time, challenger name + id, defender name + id
def initial_sheet_fill(duel_):
    global row_index
    
    sheet = open_sheets(0)
    
    sheet.update_cell(row_index, 1, duel_.id)
    sheet.update_cell(row_index, 2, duel_.time)
    sheet.update_cell(row_index, 3, duel_.challenger.name)
    sheet.update_cell(row_index, 4, str(duel_.challenger.id))
    sheet.update_cell(row_index, 6, duel_.defender.name)
    sheet.update_cell(row_index, 7, str(duel_.defender.id))

    row_index += 1

#   duel_id is obtained by taking the last four digits of the result of
#   adding the two players' ID's together and dividing this by two
def create_duel_id(challenger_id, defender_id):
    duel_id = int((challenger_id + defender_id) / 2)
    duel_id = int(str(duel_id)[-4:])

    return int(duel_id)

#   takes the respone of defender
async def respond_duel(id_, name, response, message_indicator, channel):
    
    current_duel = retrieve_duel(id_)

    if name == current_duel.defender.name:
        await current_duel.duel_response(response, message_indicator)

        if response:
            await true_response(channel)

    elif name == current_duel.challenger.name:
        response = 'Please allow the defender to !confirm or !reject the duel\n If you, as the **Challenger**, no longer wish to take the duel, please indicate so by typing !cancel'
        await channel.send(response)
    else:
        response = 'You are not a participant to the Duel'
        await channel.send(response)

async def true_response(channel):
    response = 'The Duel has been accepted! \n You now have **TWO** hours to complete the Duel! \n Good luck to both and make sure to have fun!'
    await channel.send(response)

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

async def update_cancellation_timers():
    await client.wait_until_ready()

    while not client.is_closed():
        try:

            if len(duel_clocks_list) > 0:
                
                for element in duel_clocks_list:
                    element.time_ -= 1

                    if element.time_ <= 0:
                        element.timeout()
                        del element
                        duel_clocks_list.pop(0)

                print(element.duel.id + " " + element.time_)

            if len(channels_pending_deletion) > 0:
                for channel in channels_pending_deletion:
                    await delete_channel(channel)


            if len(duels_pending_deletion) > 0:
                for duel in duels_pending_deletion:
                    await cancel_duel(duel, duel.index)
                    del duel


            await asyncio.sleep(1)

        except:
            print('Duel clocks not working')

async def cancel_duel(duel_, reason_index):

    guild_reference = duel_.channel_.guild

    firelord_role = get_firelord(guild_reference)
    challenger = duel_.challenger
    defender = duel_.defender
    at_everyone = get_at_everyone(guild_reference)

    overwrites = {
        firelord_role : discord.PermissionOverwrite(read_messages = True, send_messages = True, read_message_history=True),

        challenger: discord.PermissionOverwrite(read_messages = True, send_messages = False, read_messsage_history=True),
        
        defender: discord.PermissionOverwrite(read_messages = True, send_messages = False, read_message_history=True),

        at_everyone : discord.PermissionOverwrite(read_messages = True, send_messages = False, read_message_history=True)
    }

    duel_.channel_.edit(overwrites=overwrites)

    await duel_.channel_.send('This duel has been cancelled for the following reason: \n> ' + cancellation_reasons[reason_index] + 
                                ' \nBoth participants will be sent a private message with a confirmation \n \nThis channel will be deleted in a moment.')

    channels_pending_deletion.append(duel_.channel_)
    duels_pending_deletion.append(duel_list.pop(duel_.id))

def retrieve_duel(id_):
    global duel_list

    return duel_list[id_]

client.loop.create_task(update_cancellation_timers())
client.run(TOKEN)