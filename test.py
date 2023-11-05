import asyncio
from riotapi import RiotApi


class ApiTest:
    async def matchWin(self):
        x = await RiotApi.getMatchWin(
            {"X-Riot-Token": "RGAPI-511f61b9-4dea-44b5-9e3d-04f68c2e6081"},
            "6663249792",
            "0yzQ85TxyDM74eCUyBuQlrSrb21sTR9Z3yvnb-lYfOuEhxw",
        )
        print(x)


async def main():
    api = ApiTest()
    await api.matchWin()


if __name__ == "__main__":
    asyncio.run(main())
