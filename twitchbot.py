from twitchio.ext import commands
from riotapi import RiotApi
import asyncio
import json
from datetime import datetime, timedelta

# Define your bot's credentials and channel here
TMI_TOKEN = "oauth:pjgtujppwlnfopi6lm30r33h64fzje"
CLIENT_ID = "0ykm7wjf2lgurc4t1kxdu2ivaushnb"
BOT_NICK = "smokeyxxl"
BOT_PREFIX = "!"
CHANNEL = "virrivadilli"
SUMMONER = "LvL 2 Crook"
RIOT_API_TOKEN = "RGAPI-931f4d8a-327e-49de-b070-1621e36c2e19"


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
        self.headers = {"X-Riot-Token": "RGAPI-931f4d8a-327e-49de-b070-1621e36c2e19"}
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
        except Exception as e:
            print(f"Failed to retrieve Summoner ID: {e}")
            return  # Stop further execution if Summoner ID can't be retrieved
        self.load_balances()
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
                    if participant["win"] == "True":
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
        total_bet_amount = sum(
            bet[0] for bet in self.bets.values()
        )  # Total amount bet by everyone
        total_winning_bets = sum(
            bet[0] for bettor, bet in self.bets.items() if bet[1] == outcome
        )

        # If nobody won, skip the division to prevent division by zero
        if total_winning_bets == 0:
            await self.announce_no_winners()
            return

        # Calculate winnings for each winner
        for bettor, bet in list(
            self.bets.items()
        ):  # Create a copy of the dictionary items
            bet_amount, bet_outcome = bet
            if bet_outcome == outcome:
                # Winner's share is proportionate to their bet relative to total winning bets
                winner_share = (bet_amount / total_winning_bets) * total_bet_amount
                # Update the user's balance with their winnings
                self.user_balances[bettor] += winner_share
                await self.announce_winner(bettor, winner_share)
            else:
                # Losers have already had their bet amounts deducted when they placed their bet
                await self.announce_loser(bettor)

        # Announce the results here
        channel = self.get_channel(CHANNEL)
        await channel.send(f"The match has ended in a {outcome}!")
        self.bets.clear()
        self.save_balances()

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
            self.user_balances[
                ctx.author.name
            ] = 100  # Give new users some starting currency

        if amount <= 0 or amount > self.user_balances[ctx.author.name]:
            return await ctx.send("Invalid bet amount.")

        # Allow only "win" or "loss" as valid outcomes
        if outcome not in ["win", "loss"]:
            return await ctx.send(
                "Invalid outcome. You can only bet on 'win' or 'loss'."
            )

        # Record the user's bet
        self.bets[ctx.author.name] = (amount, outcome)
        # Deduct the bet amount from the user's balance
        self.user_balances[ctx.author.name] -= amount
        await ctx.send(f"{ctx.author.name} has bet {amount} on {outcome}!")

        # Calculate the total amounts bet on each outcome
        total_on_win = sum(
            bet[0] for bettor, bet in self.bets.items() if bet[1] == "win"
        )
        total_on_loss = sum(
            bet[0] for bettor, bet in self.bets.items() if bet[1] == "loss"
        )

        # Announce the total amounts bet on "win" and "loss"
        await ctx.send(f"Total on win: {total_on_win}, Total on loss: {total_on_loss}")

    @commands.command(name="balance")
    async def balance(self, ctx):
        balance = self.user_balances.get(ctx.author.name, 0)
        await ctx.send(f"{ctx.author.name}, you have {balance} rejuvenation beads.")

    @commands.command(name="farm")
    async def farm(self, ctx):
        current_time = datetime.utcnow()
        user_data = self.user_balances.get(
            ctx.author.name, {"balance": 0, "last_farm": None}
        )

        # Check if the user has farmed before
        if user_data["last_farm"]:
            last_farm_time = user_data["last_farm"]
            # Check if 24 hours have passed since the last farm
            if current_time - last_farm_time < timedelta(days=1):
                time_diff = timedelta(days=1) - (current_time - last_farm_time)
                hours, remainder = divmod(int(time_diff.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                return await ctx.send(
                    f"You must wait {hours}h {minutes}m {seconds}s to farm again."
                )

        # If the user is farming for the first time or 24 hours have passed
        new_balance = user_data["balance"] + 3
        self.user_balances[ctx.author.name] = {
            "balance": new_balance,
            "last_farm": current_time,
        }

        await ctx.send(f"{ctx.author.name}, you have farmed 3 rejuvenation beads.")
        self.save_balances()

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
        with open("user_data.json", "w") as f:
            # Convert datetime objects to strings for JSON serialization
            data_to_save = {
                user: {
                    "balance": data["balance"],
                    "last_farm": data["last_farm"].isoformat()
                    if data.get("last_farm")
                    else None,
                }
                for user, data in self.user_balances.items()
            }
            json.dump(data_to_save, f)

    def load_balances(self):
        try:
            with open("user_data.json", "r") as f:
                data_loaded = json.load(f)
                # Convert datetime strings back to datetime objects
                self.user_balances = {
                    user: {
                        "balance": data["balance"],
                        "last_farm": datetime.fromisoformat(data["last_farm"])
                        if data["last_farm"]
                        else None,
                    }
                    for user, data in data_loaded.items()
                }
        except FileNotFoundError:
            print("User data file does not exist, starting with empty balances.")
            self.user_balances = {}


# This part runs the bot
if __name__ == "__main__":
    bot = Bot()
    bot.loop.create_task(bot.check_for_match())
    bot.run()
