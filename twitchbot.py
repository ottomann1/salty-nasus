from twitchio.ext import commands
from riotapi import RiotApi
import asyncio
import json
from datetime import datetime, timedelta

# Define your bot's credentials and channel here
TMI_TOKEN = ""
CLIENT_ID = ""
BOT_NICK = ""
BOT_PREFIX = "!"
CHANNEL = ""
SUMMONER = ""
RIOT_API_TOKEN = ""


class Bot(commands.Bot):
    def __init__(self):
        super().__init__(
            token=TMI_TOKEN,
            client_id=CLIENT_ID,
            nick=BOT_NICK,
            prefix=BOT_PREFIX,
            initial_channels=[CHANNEL],
        )
        self.bets = {}
        self.user_balances = {}
        self.is_accepting_bets = False
        self.summoner = SUMMONER
        self.headers = {"X-Riot-Token": RIOT_API_TOKEN}
        self.gameId = None

    async def event_ready(self):
        """Called once when the bot goes online."""
        print(f"Logged in as | {self.nick}")
        try:
            summonerjson = await RiotApi.getSummonerId(self.headers, self.summoner)
            self.summonerId = summonerjson["id"]
            self.summonerPuuid = summonerjson["puuid"]
            print(f"Summoner ID: {self.summonerId}")
            print(f"Summoner PUUID: {self.summonerPuuid}")
            self.load_balances()
        except Exception as e:
            print(f"Failed to retrieve Summoner ID: {e}")
            return  # Stop further execution if Summoner ID can't be retrieved

        self.loop.create_task(self.check_for_match())

    async def event_message(self, message):
        await self.handle_commands(message)

    async def check_for_match(self):
        while True:
            if not self.is_accepting_bets:
                match = await RiotApi.getMatch(self.headers, self.summonerId)
                if match.get("status") and match["status"]["status_code"] == 404:
                    # If the match has ended and status code 404 is returned
                    if self.gameId:
                        # Only check match result if we previously had a game going on
                        result_check = await self.check_match_result()
                        if (
                            result_check
                        ):  # Ensure that we have got the result before resetting
                            self.gameId = None  # Reset the gameId
                            self.is_accepting_bets = False
                            print(
                                "Match ended. Waiting before checking for a new match."
                            )
                            await asyncio.sleep(
                                240
                            )  # Wait for 4 minutes before checking for a new match
                elif match.get("gameId"):
                    # Match is in progress
                    if not self.gameId:
                        self.gameId = match["gameId"]
                        self.is_accepting_bets = True
                        await self.announce_bets_open()
            else:
                # If bets are being accepted, check if the match has concluded every so often
                match = await RiotApi.getMatch(self.headers, self.summonerId)
                if match.get("status") and match["status"]["status_code"] == 404:
                    self.is_accepting_bets = False  # Match has ended, close bets

            await asyncio.sleep(30)  # Regular check every 10 seconds

    async def check_match_result(self):
        retries = 0
        result_acquired = False
        while (
            not result_acquired and retries < 30
        ):  # Limit retries to prevent infinite loop
            try:
                # Check the match result here
                participant = await RiotApi.getMatchWin(
                    self.headers, self.gameId, self.summonerId
                )
                if participant.get("win") is not None:
                    if participant["win"] == True:
                        await self.resolve_bets("win")
                    else:
                        await self.resolve_bets("loss")
                    result_acquired = True
                else:
                    retries += 1
                    await asyncio.sleep(10)  # Wait for 10 seconds before retrying
            except Exception as e:
                print(f"Error checking match result: {e}")
                retries += 1
                await asyncio.sleep(10)

        return result_acquired

    async def resolve_bets(self, outcome):
        for bettor, bet in list(self.bets.items()):  # Iterate over a copy of all bets
            bet_amount, bet_outcome = bet
            if bet_outcome == outcome:
                # If the user won, they receive twice their bet amount
                winner_payout = bet_amount * 2
                self.user_balances[bettor]["balance"] += winner_payout
                await self.announce_winner(bettor, winner_payout)
            else:
                # Losers have already had their bet amounts deducted when they placed their bet
                await self.announce_loser(bettor)

        # Clear all bets after resolving them
        self.bets.clear()
        # Save the updated user balances to file
        self.save_balances()

    # async def resolve_bets(self, outcome):
    #     total_bet_amount = sum(
    #         bet[0] for bet in self.bets.values()
    #     )  # Total amount bet by everyone
    #     total_winning_bets = sum(
    #         bet[0] for bettor, bet in self.bets.items() if bet[1] == outcome
    #     )

    #     # If nobody won, skip the division to prevent division by zero
    #     if total_winning_bets == 0:
    #         await self.announce_no_winners()
    #         return

    #     # Calculate winnings for each winner
    #     for bettor, bet in list(
    #         self.bets.items()
    #     ):  # Create a copy of the dictionary items
    #         bet_amount, bet_outcome = bet
    #         if bet_outcome == outcome:
    #             # Winner's share is proportionate to their bet relative to total winning bets
    #             winner_share = (bet_amount / total_winning_bets) * total_bet_amount
    #             # Update the user's balance with their winnings
    #             self.user_balances[bettor]["balance"] += winner_share
    #             await self.announce_winner(bettor, winner_share)
    #         else:
    #             # Losers have already had their bet amounts deducted when they placed their bet
    #             await self.announce_loser(bettor)

    #     # Announce the results here
    #     channel = self.get_channel(CHANNEL)
    #     await channel.send(f"The match has ended in a {outcome}!")
    #     self.bets.clear()
    #     self.save_balances()

    async def announce_winner(self, bettor, amount):
        channel = self.get_channel(CHANNEL)
        await channel.send(f"Congratulations {bettor}, you won {amount:.2f}!")

    async def announce_loser(self, bettor):
        channel = self.get_channel(CHANNEL)
        await channel.send(f"Sorry {bettor}, you lost your bet.")

    async def announce_no_winners(self):
        channel = self.get_channel(CHANNEL)
        await channel.send("No winners this time, better luck next match!")

    @commands.command(name="bet")
    async def bet(self, ctx, amount: int, outcome: str):
        if not self.is_accepting_bets:
            # Send a message to the user if betting is not allowed at the moment
            return await ctx.send("Betting is currently closed.")

        if ctx.author.name not in self.user_balances:
            return await ctx.send(
                "You are not registered. Use !register to start betting."
            )

        if amount <= 0 or amount > self.user_balances[ctx.author.name]["balance"]:
            return await ctx.send("Invalid bet amount.")

        # Allow only "win" or "loss" as valid outcomes
        if outcome not in ["win", "loss"]:
            return await ctx.send(
                "Invalid outcome. You can only bet on 'win' or 'loss'."
            )

        self.bets[ctx.author.name] = (amount, outcome)
        self.user_balances[ctx.author.name]["balance"] -= amount
        await ctx.send(f"{ctx.author.name} has bet {amount} on {outcome}!")

    @commands.command(name="balance")
    async def balance(self, ctx):
        balance = self.user_balances.get(ctx.author.name, 0)
        balance = balance["balance"]
        await ctx.send(f"{ctx.author.name}, you have {balance} rejuvenation beads.")

    @commands.command(name="register")
    async def register(self, ctx):
        # Check if the user is already registered
        if ctx.author.name in self.user_balances:
            return await ctx.send("You are already registered!")

        # Register the user with a starting balance of 100 beads
        self.user_balances[ctx.author.name] = {
            "balance": 100,
            "last_farm": datetime.utcnow(),
        }

        # Acknowledge the registration
        await ctx.send(
            f"{ctx.author.name}, you have been registered with 100 rejuvenation beads!"
        )

        # Save the updated balances
        self.save_balances()

    @commands.command(name="farm")
    async def farm(self, ctx):
        if ctx.author.name not in self.user_balances:
            return await ctx.send(
                "You are not registered. Use !register to start farming."
            )

        current_time = datetime.utcnow()
        user_data = self.user_balances[ctx.author.name]

        # Check if the user exists and has farmed before
        if user_data:
            last_farm_time = datetime.fromisoformat(user_data["last_farm"])
            # Check if 24 hours have passed since the last farm
            if current_time - last_farm_time < timedelta(days=1):
                time_diff = timedelta(days=1) - (current_time - last_farm_time)
                hours, remainder = divmod(int(time_diff.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                return await ctx.send(
                    f"You must wait {hours}h {minutes}m {seconds}s to farm again."
                )

        # If the user is farming for the first time or 24 hours have passed
        self.user_balances[ctx.author.name] = {
            "balance": user_data["balance"] + 3 if user_data else 3,
            "last_farm": current_time,
        }
        await ctx.send(f"{ctx.author.name}, you have farmed 3 rejuvenation beads.")
        self.save_balances()

    @commands.command(name="top")
    async def top(self, ctx):
        # Make sure there are balances to sort and display
        if not self.user_balances:
            return await ctx.send("No users to display.")

        # Retrieve and sort the balances in descending order
        sorted_balances = sorted(
            self.user_balances.items(),
            key=lambda item: item[1]["balance"],
            reverse=True,
        )

        # Create a message with the sorted balances
        message = "Top balances:\n"
        for index, (user, data) in enumerate(sorted_balances, start=1):
            message += f"{index}. {user} - {data['balance']} beads \n"

            # Send the message in chunks if it gets too long
            if len(message) >= 400:  # Twitch messages have a limit
                await ctx.send(message)
                message = ""

        # Send any remaining message part
        if message:
            await ctx.send(message)

    async def announce_bets_open(self):
        self.is_accepting_bets = True
        channel = self.get_channel(CHANNEL)
        await channel.send("Bets are open! You have 5 minutes to place your bets.")
        # Create a task to close bets after 5 minutes
        self.loop.create_task(self.close_bets())

    async def close_bets(self):
        # Wait for 5 minutes (300 seconds)
        await asyncio.sleep(60)
        channel = self.get_channel(CHANNEL)
        await channel.send("4 minutes remaining")
        await asyncio.sleep(60)
        await channel.send("3 minutes remaining")
        await asyncio.sleep(60)
        await channel.send("2 minutes remaining")
        await asyncio.sleep(60)
        await channel.send("1 minutes remaining")
        await asyncio.sleep(30)
        await channel.send("30 seconds remaining")
        await asyncio.sleep(20)
        await channel.send("10 seconds remaining")
        await asyncio.sleep(10)
        self.is_accepting_bets = False
        await channel.send("Betting is now closed. Good luck!")

        # Save to file

    def save_balances(self):
        # Convert datetime objects to string before saving to JSON
        for user, data in self.user_balances.items():
            if "last_farm" in data and isinstance(data["last_farm"], datetime):
                data["last_farm"] = data["last_farm"].isoformat()

        with open("balances.json", "w") as f:
            json.dump(self.user_balances, f)

    def load_balances(self):
        try:
            with open("balances.json", "r") as f:
                self.user_balances = json.load(f)
            # Convert strings back to datetime objects
            for user, data in self.user_balances.items():
                if "last_farm" in data:
                    data["last_farm"] = datetime.fromisoformat(data["last_farm"])
        except FileNotFoundError:
            self.user_balances = {}


# This part runs the bot
if __name__ == "__main__":
    bot = Bot()
    bot.loop.create_task(bot.check_for_match())
    bot.run()
