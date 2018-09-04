from typing import Optional, Dict, Tuple, List

import requests
from pyjsparser import PyJsParser
from pyquery import PyQuery as pq
from requests.cookies import RequestsCookieJar

# The User-Agent header used for all requests
HEADER_UA = {
    "User-Agent": "Mozilla/5.0"
}

# The domains used in the API
VANIER_DOMAIN = "https://vaniercollege.omnivox.ca"
LEA_DOMAIN = "https://vaniercollege-estd.omnivox.ca/estd"

# The global JS parser
JS_PARSER = PyJsParser()


class OmnivoxSemester:
    """
    Represents a semester.
    """

    def __init__(self, semester_id: str, semester_name: str, current: bool):
        """
        Initializes a semester instance.
        :param semester_id: The ID of the semester. The format is usually Year(+)Index, e.g. 20181
        :param semester_name: The name of the semester. Example: Fall 2018
        :param current: Whether this semester is the current semester.
        """
        self.id = semester_id
        self.name = semester_name
        self.current = current

    def __repr__(self) -> str:
        return f"Semester(id={self.name}, name={self.id}, current={self.current})"


class OmnivoxSemesterScheduleCourse:
    """
    Represents a course inside a semester schedule.
    """

    def __init__(self, number, section, title, teacher):
        """
        Initializes a course inside a semester schedule.
        :param number: The number of the course, e.g. 345-102-MQ.
        :param section: The section number of the course, e.g. 00001.
        :param title: The title of the course.
        :param teacher: The full name of the course's teacher.
        """
        self.number = number
        self.section = section
        self.title = title
        self.teacher = teacher

    def __repr__(self) -> str:
        return f"Course(number={self.number}, section={self.section}, title={self.title}, teacher={self.teacher})"


class OmnivoxSemesterSchedule:
    """
    Represents a semester schedule.
    """

    def __init__(self, semester: OmnivoxSemester, courses: Tuple[OmnivoxSemesterScheduleCourse]):
        """
        Initializes a semester schedule.
        :param semester: The semester for this schedule.
        :param courses: A tuple of courses inside this schedule.
        """
        self.semester = semester
        self.courses = courses


class LeaScheduleSelectionPage:
    """
    Represents the page to request schedules in LEA.
    """

    def __init__(self, session, schedule_reference: str):
        """
        Initializes a wrapper over the LEA schedule request page.

        :param session: The Omnivox session used to authenticate the LEA requests.
        :param schedule_reference: The schedule request reference.
        """
        self.cookies = RequestsCookieJar()
        self.cookies.update(session.cookies)
        self.schedule_reference = schedule_reference

        self._semesters: Tuple[OmnivoxSemester] = None
        self._schedule_cache: Dict[str, OmnivoxSemesterSchedule] = dict()
        self._schedule_request_url: str = None

    async def fetch(self):
        """
        Fetches the page, including the ID of the available semesters.
        :return: Nothing
        """
        schedule_page_response = requests.get(
            url=VANIER_DOMAIN + self.schedule_reference,
            headers=HEADER_UA,
            cookies=self.cookies
        )
        self.cookies.update(schedule_page_response.cookies)

        body_redirect_location = get_js_redirect(pq(schedule_page_response.text)("body"))
        session_load_url = LEA_DOMAIN + "/" + body_redirect_location
        session_load_response = requests.get(
            url=session_load_url,
            headers=HEADER_UA,
            cookies=self.cookies
        )
        self.cookies.update(session_load_response.cookies)

        schedule_page_response = requests.get(
            url=LEA_DOMAIN + "/hrre/horaire.ovx",
            headers=HEADER_UA,
            cookies=self.cookies
        )

        semesters = []
        page_d = pq(schedule_page_response.text)
        for option in page_d("select[name='AnSession']").children("option"):
            option_d = pq(option)
            semesters.append(
                OmnivoxSemester(option_d.val(), option_d.text(), option_d.attr("selected") is not None)
            )

        self._semesters = tuple(semesters)
        self._schedule_request_url = LEA_DOMAIN + "/hrre/" + page_d("form").attr("action")

    async def get_current_semester(self) -> Optional[OmnivoxSemester]:
        """
        Retrieves the ID of the current semester, if any.
        """
        if not self._semesters:
            await self.fetch()

        for semester in self._semesters:
            if semester.current:
                return semester
        return None

    async def get_all_semesters(self) -> Tuple[OmnivoxSemester]:
        """
        Retrieves the ID of all the available semesters.
        """
        if not self._semesters:
            await self.fetch()

        return tuple(self._semesters)

    async def get_schedule(self, semester: OmnivoxSemester, force=False) -> OmnivoxSemesterSchedule:
        """
        Gets and caches the schedule for the given semester.
        :param semester: The semester whose schedule is being requested.
        :param force: Whether to ignore the cache for the schedules.
        :return: An object representing the schedule for the requested semester.
        """
        if not self._semesters:
            await self.fetch()

        if not force:
            if semester.id in self._schedule_cache:
                return self._schedule_cache[semester.id]

        schedule_request_response = requests.post(
            url=self._schedule_request_url,
            headers=HEADER_UA,
            cookies=self.cookies,
            data={
                "AnSession": semester.id,
                "Confirm": "Obtain+my+schedule"
            }
        )

        body_redirect_location = LEA_DOMAIN + "/hrre/" + get_js_redirect(pq(schedule_request_response.text)("body"))
        schedule_page_response = requests.get(
            url=body_redirect_location,
            headers=HEADER_UA,
            cookies=self.cookies
        )

        # Parse the schedule page
        courses: List[OmnivoxSemesterScheduleCourse] = []
        schedule_d = pq(schedule_page_response.text)

        # Check if there is no warning - if there is, there are no courses for this semester.
        if not schedule_d(".tbAvertissement"):
            schedule_course_list_table = pq(schedule_d(".tbContenantPageLayout table table")[3])
            course_list_rows = schedule_course_list_table.children("tr")

            for i in range(3, len(course_list_rows) - 1):
                course_row = pq(course_list_rows[i])
                course_number = pq(course_row.children("td")[1])("span").text()
                course_section = pq(course_row.children("td")[2])("span").text()
                course_title = pq(course_row.children("td")[3])("span").text()
                teacher = pq(course_row.children("td")[4])("a").text()

                courses.append(
                    OmnivoxSemesterScheduleCourse(
                        number=course_number,
                        section=course_section,
                        title=course_title,
                        teacher=teacher
                    )
                )

        schedule = OmnivoxSemesterSchedule(
            semester=semester,
            courses=tuple(courses)
        )
        self._schedule_cache[semester.id] = schedule
        return schedule


class OmnivoxSession:
    def __init__(self, cookies: RequestsCookieJar, homepage_html: str):
        self.cookies = cookies
        self.homepage_html = homepage_html
        self._homepage_d = pq(homepage_html)

    def get_schedule_page(self) -> LeaScheduleSelectionPage:
        schedule_link_node = self._homepage_d("#ctl00_partOffreServices_offreV2_HOR")
        page = LeaScheduleSelectionPage(self, schedule_link_node.attr("href"))
        return page

    def get_user_fullname(self) -> str:
        return self._homepage_d("#ovx10_user_text").text()


async def login(student_id, student_password) -> Optional[OmnivoxSession]:
    login_page_response = requests.get(
        "https://vaniercollege.omnivox.ca/intr/Module/Identification/Login/Login.aspx?ReturnUrl=/intr",
        headers=HEADER_UA
    )
    d = pq(login_page_response.text)
    k = d("input[name='k']").attr("value")

    login_form = {
        "NoDA": student_id,
        "PasswordEtu": student_password,
        "TypeIdentification": "Etudiant",
        "k": k
    }
    login_post_response = requests.post(
        url="https://vaniercollege.omnivox.ca/intr/Module/Identification/Login/Login.aspx?ReturnUrl=/intr",
        data=login_form,
        headers=HEADER_UA,
        cookies=login_page_response.cookies,
        allow_redirects=False
    )

    if login_post_response.status_code != 302:
        return None

    cookies = login_page_response.cookies
    cookies.update(login_post_response.cookies)

    homepage_response = requests.post(
        url="https://vaniercollege.omnivox.ca/intr/",
        headers=HEADER_UA,
        cookies=cookies,
        allow_redirects=False
    )
    cookies.update(homepage_response.cookies)

    return OmnivoxSession(
        cookies=cookies,
        homepage_html=homepage_response.text
    )


def get_js_redirect(tag) -> str:
    """
    Retrieves the target location of a JS auto redirect.
    :param tag: the body tag containing the onload attribute.
    :return: the target location.
    """
    raw = tag.attr("onload")
    js = JS_PARSER.parse(raw)
    return js["body"][0]["expression"]["arguments"][0]["value"]
