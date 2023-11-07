import asyncio
from riotapi import RiotApi


class ApiTest:
    async def matchWin(self):
        x = await RiotApi.getMatchWin(
            {"X-Riot-Token": "RGAPI-931f4d8a-327e-49de-b070-1621e36c2e19"},
            "6663249792",
            "0yzQ85TxyDM74eCUyBuQlrSrb21sTR9Z3yvnb-lYfOuEhxw",
        )
        print(x)


async def main():
    api = ApiTest()
    await api.matchWin()


if __name__ == "__main__":
    asyncio.run(main())
