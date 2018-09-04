import asyncio
import os
from pprint import pprint

import omnivox

"""
Demonstration for the Vanier Omnivox wrapper.
"""


async def run():
    # login to Omnivox using credentials
    sess = await omnivox.login(
        os.environ.get("OMNIVOX_ID", default=""),
        os.environ.get("OMNIVOX_PASSWORD", default="")
    )
    # login failed
    if not sess:
        print("Login failed!")
        return

    # get the current user's full name
    print("User full name: " + sess.get_user_fullname())

    # get the schedule for the current semester
    schedule_page = sess.get_schedule_page()
    semester = await schedule_page.get_current_semester()
    schedule = await schedule_page.get_schedule(semester)

    # list the courses for the current semester
    pprint(schedule.grid.grid)


if __name__ == '__main__':
    # run demo in main event loop
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())
