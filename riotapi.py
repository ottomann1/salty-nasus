import aiohttp


class RiotApi:
    @staticmethod
    async def getSummonerId(headers: dict, summoner: str):
        url = f"https://euw1.api.riotgames.com/lol/summoner/v4/summoners/by-name/{summoner}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                jsonresp = await response.json()
                print(jsonresp)
                return jsonresp

    @staticmethod
    async def getMatch(headers: dict, summonerId: str):
        url = f"https://euw1.api.riotgames.com/lol/spectator/v4/active-games/by-summoner/{summonerId}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                jsonresp = await response.json()
                print(jsonresp)
                return jsonresp

    @staticmethod
    async def getMatchWin(headers: dict, gameId: str, summonerId: str):
        url = f"https://europe.api.riotgames.com/lol/match/v5/matches/EUW1_{gameId}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                jsonresp = await response.json()
                jsonresp = jsonresp["info"]
                print(jsonresp)
                for participant in jsonresp["participants"]:
                    print(participant)
                    if participant["summonerId"] == summonerId:
                        return participant
