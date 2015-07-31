#! /usr/bin/env python2
from jira import JIRA
from datetime import date, timedelta
import dateutil.parser
import time
import getpass
import smtplib
import argparse
import re

# TODO:
#	Open code reviews with age more 2 days
#	Weekly metrics
#	Monthly project metrics

server = "http://adc.luxoft.com/jira"
current_sprint = "SDL_RB_B3.20"
users = ["dtrunov ", "agaliuzov", "akutsan", "aoleynik", "anosach", "okrotenko", "vveremjova",
         "abyzhynar", "ezamakhov", "aleshin", "akirov", "vprodanov", "alambin"]

message_template = '''From: Alexander Kutsan <AKutsan@luxoft.com>
To: %s
Subject: Metric fails WARNING

Hello,

Metric fails collected by script:

%s

Script sources available on github
https://github.com/LuxoftAKutsan/SDLMetricsCollector

Best regards,
Alexander Kutsan
'''


def is_holiday(day):
    return day.weekday() > 4


def time_spent_from_str(time_spent):
    res = 0
    minutes = re.search("([0-9]+)m", time_spent)
    hours = re.search("([0-9]+)h", time_spent)
    days = re.search("([0-9]+)d", time_spent)
    if days:
        res += int(days.groups()[0]) * 8.0
    if hours:
        res += int(hours.groups()[0])
    if minutes:
        res += int(minutes.groups()[0]) / 60.0
    return res


def calc_diff_days(from_date, to_date):
    from_date = from_date.split("-")
    to_date = to_date.split("-")
    from_date = date(int(from_date[0]), int(from_date[1]), int(from_date[2]))
    to_date = date(int(to_date[0]), int(to_date[1]), int(to_date[2]))
    day_generator = (from_date + timedelta(x + 1) for x in range((to_date - from_date).days))
    return sum(1 for day in day_generator if not is_holiday(day))


def last_work_day():
    day = date.today() - timedelta(1)
    while is_holiday(day):
        day -= timedelta(1)
    return day


def to_h(val):
    return val / 60.0 / 60.0


class SDL():
    issue_path = "https://adc.luxoft.com/jira/browse/%s"

    def __init__(self, user, passwd, developers_on_vacation=[], developers=users):
        self.jira = JIRA(server, basic_auth=(user, passwd))
        self.on_vacation = developers_on_vacation
        self.developers = developers
        self.sdl = self.jira.project('APPLINK')
        versions = self.jira.project_versions(self.sdl)
        for v in versions:
            if v.name == current_sprint:
                self.sprint = v
                break

    def workload(self, user, report=[]):
        query = 'assignee = %s AND status not in (Suspended, Closed, Resolved) AND fixVersion in("%s")'
        issues = self.jira.search_issues(query % (user, self.sprint))
        res = 0
        for issue in issues:
            if issue.fields.timeestimate:
                res += to_h(issue.fields.timeestimate)
                report.append((issue, to_h(issue.fields.timeestimate)))
            else:
                print("Not estimated issue %s (%s)" % (issue, user))
        return res

    def calc_overload(self):
        report = []
        for user in self.developers:
            load = self.workload(user)
            today = time.strftime("%Y-%m-%d")
            days_left = calc_diff_days(today, self.sprint.releaseDate)
            hours_left = days_left * 8
            overload = hours_left - load
            #res = "OK"
            if (overload < 0):
                res = "OVERLOAD : %s" % (-overload)
                print("%s overload : %s h  (%s/%s)" % (user, -overload, load, hours_left))
                report_str = "%s/%s : %s" % (load, hours_left, res)
                report.append((user, report_str))
        return report

    def issues_without_due_date(self):
        report = []
        for user in self.developers:
            query = ''' assignee = %s and type not in (Question) AND fixversion in ("%s")  AND status not in (Closed, Resolved, Suspended) AND duedate is EMPTY '''
            issues = self.jira.search_issues(query % (user, self.sprint))
            for issue in issues:
                report.append((user, self.issue_path % issue))
                print("%s has issue without estimate %s" % (user, issue))
        return report


    def issues_with_expired_due_date(self):
        report = []
        for user in self.developers:
            query = ''' assignee = %s and status not in (closed, resolved, Approved) AND duedate < startOfDay()'''
            issues = self.jira.search_issues(query % user)
            for issue in issues:
                report.append((user, self.issue_path % issue))
                print("%s has issue with expired due date %s" % (user, issue))
        return report


    def expired_in_progress(self):
        report = []
        for user in self.developers:
            query = ''' assignee = %s AND status = "In Progress" AND (updated < -2d OR fixVersion = Backlog)'''
            issues = self.jira.search_issues(query % user)
            for issue in issues:
                report.append((user, self.issue_path % issue))
                print("%s has issue in Progress that wasn't updated more then 2 days %s" % (user, issue))
        return report


    def without_correct_estimation(self):
        report = []
        for user in self.developers:
            query = ''' assignee = %s and type not in (Question) AND fixversion in ("%s") AND status not in (Closed, Resolved, Suspended) AND (remainingEstimate = 0 OR remainingEstimate is EMPTY)'''
            issues = self.jira.search_issues(query % (user, self.sprint))
            for issue in issues:
                report.append((user, self.issue_path % issue))
                print("%s has issue without correct estimation %s" % (user, issue))
        return report


    def wrong_due_date(self):
        report = []
        for user in self.developers:
            query = ''' assignee = %s and type not in (Question) AND fixversion in ("%s") AND (duedate < "%s" OR duedate > "%s") AND status not in (resolved, closed)'''
            issues = self.jira.search_issues(
                query % (user, self.sprint, self.sprint.startDate, self.sprint.releaseDate))
            for issue in issues:
                report.append((user, self.issue_path % issue))
                print("%s has issue with  wrong due date %s" % (user, issue))
        return report


    def wrong_fix_version(self):
        report = []
        for user in self.developers:
            query = '''assignee = %s AND fixversion not in ("%s") and (labels is EMPTY OR labels != exclude_from_metrics) AND status not in (closed, resolved) AND duedate > "%s" AND duedate <= "%s" '''
            issues = self.jira.search_issues(
                query % (user, self.sprint, self.sprint.startDate, self.sprint.releaseDate))
            for issue in issues:
                report.append((user, self.issue_path % issue))
                print("%s has issue with wrong fix version %s" % (user, issue))
        return report

    def absence_in_progress(self):
        report = []
        for user in self.developers:
            if user in self.on_vacation:
                continue
            query = '''assignee = %s AND status = "In Progress" '''
            issues = self.jira.search_issues(query % user)
            if (len(issues) == 0):
                report.append((user, None))
                print("%s has no issues in Progress" % user)
        return report

    def not_implemented_yet(self):
        report = []
        report.append((None, "ERROR:  Feature is not implemented yet"))
        return report

    def not_logged_vacation(self):
        report = []
        vacation_issue_key = "APPLINK-13266"
        work_logs = self.jira.worklogs(vacation_issue_key)
        yesterday_work_logs = []
        yesterday = date.today() - timedelta(1)
        for work_log in work_logs:
            date_started = dateutil.parser.parse(work_log.started).date
            if yesterday == date_started:
                yesterday_work_logs.append(date_started)
        for user in self.on_vacation:
            logged = False
            for work_log in yesterday_work_logs:
                if worklog.author.name == user:
                    logged = True
            if not logged:
                report.append((user, " Not logged vacation for " + yesterday.strftime('%Y-%m-%d')))
        return report

    def not_logged_work(self):
        report = []
        user_logged = {}
        for developer in self.developers:
            user_logged[developer] = 0
        today = date.today()
        last_work = last_work_day()
        query = '''key in workedIssues("%s","%s", "APPLINK Developers")''' % (last_work.strftime("%Y/%m/%d"),
                                                                              today.strftime("%Y/%m/%d"))
        issues = self.jira.search_issues(query)
        for issue in issues:
            work_logs = self.jira.worklogs(issue.key)
            for work_log in work_logs:
                date_started = dateutil.parser.parse(work_log.started).date()
                if date_started == last_work:
                    time_spent = work_log.timeSpent
                    author = work_log.updateAuthor.name
                    if author in self.developers:
                        user_logged[author] += time_spent_from_str(time_spent)
        for developer in user_logged:
            if (user_logged[developer] < 8):
                report.append(
                    (developer, "Logged for %s : %sh" % (last_work.strftime("%Y/%m/%d"), user_logged[developer])))
        return report

    def daily_metrics(self):
        report = {}
        report[
            '1. Tickets with incorrect or empty due date (except ongoing activities)'] = self.issues_without_due_date()
        report['2. Tickets with expired due dates'] = self.issues_with_expired_due_date()
        report['3. Absence of "in progress" issues assigned to each team member report'] = self.absence_in_progress()
        report['4. Tickets "in progress" without updating during last 2 days'] = self.expired_in_progress()
        report['5. Open issues without correct estimation'] = self.without_correct_estimation()
        report['6. Open code reviews with age more 2 days'] = self.not_implemented_yet()
        report['7. Overload : '] = self.calc_overload()
        report['8. Previous day work time logging'] = self.not_logged_work()
        report['9. Not logged vacation'] = self.not_logged_vacation()
        report['10. Tickets with wrong FixVersion'] = self.wrong_fix_version()
        report['11. Wrong due date'] = self.wrong_due_date()
        return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-m", "--send_mail", action="store_true",
                        help="Send emails about result")
    parser.add_argument("-v", "--vacation", action="store", nargs='+',
                        help="Developer on vacation")
    parser.add_argument("-d", "--developers", action="store", nargs='+',
                        help="Custom developers list")
    args = parser.parse_args()
    user = raw_input("Enter JIRA username : ")
    passwd = getpass.getpass()
    developers = users
    if args.developers:
        developers = args.developers
    on_vacation = []
    if args.vacation:
        on_vacation = args.vacation
    sdl = SDL(user, passwd, developers_on_vacation=on_vacation, developers=developers)
    daily_report = sdl.daily_metrics()
    email_list = []
    email_template = "%s@luxoft.com"
    report_str = ""
    for metric in daily_report:
        temp = "%s : \n" % metric
        report_str += temp
        fails = daily_report[metric]
        for fail in fails:
            temp = "\t%s : %s \n" % (fail[0], fail[1])
            report_str += temp
            if fail[0]:
                email = email_template % (fail[0])
                if email not in email_list:
                    email_list.append(email)
    print(report_str)
    if (args.send_mail):
        print(email_list)
        sender = '%s@luxoft.com' % user
        smtpObj = smtplib.SMTP('puppy.luxoft.com')
        smtpObj.sendmail(sender, email_list, message_template % (";".join(email_list), report_str))

    return 0


if __name__ == "__main__":
    main()
