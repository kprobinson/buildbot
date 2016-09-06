# This file is part of Buildbot.  Buildbot is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, version 2.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Copyright Buildbot Team Members

"""
This files implement buildbotNetStatistics options
It uses urllib2 instead of requests in order to avoid requiring another dependency for statistics feature.
urllib2 supports http_proxy already urllib2 is blocking and thus everything is done from a thread.
"""
import inspect
import json
import platform
import urllib2

from twisted.internet import threads
from twisted.python import log

from buildbot.process.buildstep import _BuildStepFactory
from buildbot.www.config import IndexResource

# This can't change! or we will need to make sure we are compatible with all
# released version of buildbot >=0.9.0
PHONE_HOME_URL = "https://events.buildbot.net/events/phone_home"


def get_distro():
    for distro in ('linux_distribution', 'mac_ver', 'win32_ver', 'java_ver'):
        if hasattr(platform, distro):
            return getattr(platform, distro)()


def getName(obj):
    """This method finds the first parent class which is within the buildbot namespace
    it prepends the name with as many ">" as the class is subclassed
    """
    if isinstance(obj, _BuildStepFactory):
        klass = obj.factory
    else:
        klass = type(obj)
    name = ""
    klasses = (klass, ) + inspect.getmro(klass)
    for klass in klasses:
        if hasattr(klass, "__module__") and klass.__module__.startswith("buildbot."):
            return name + klass.__module__ + "." + klass.__name__
        else:
            name += ">"
    return type(obj).__name__


def countPlugins(plugins_uses, l):
    if isinstance(l, dict):
        l = l.values()
    for i in l:
        name = getName(i)
        plugins_uses.setdefault(name, 0)
        plugins_uses[name] += 1


def basicData(master):

    plugins_uses = {}
    countPlugins(plugins_uses, master.config.workers)
    countPlugins(plugins_uses, master.config.builders)
    countPlugins(plugins_uses, master.config.schedulers)
    countPlugins(plugins_uses, master.config.services)
    countPlugins(plugins_uses, master.config.change_sources)
    for b in master.config.builders:
        countPlugins(plugins_uses, b.factory.steps)

    return {
        'versions': dict(IndexResource.getEnvironmentVersions()),
        'platform': {
            'machine': platform.machine(),
            'processor': platform.processor(),
            'python_implementation': platform.python_implementation(),
            # xBSD including osx will disclose too much information after [4] like where it was built
            'version': " ".join(platform.version().split(' ')[:4]),
            'distro:': get_distro()
        },
        'plugins': plugins_uses,
        'db': master.config.db['db_url'].split("://")[0],
        'mq': master.config.mq['type'],
        'www_plugins': master.config.www['plugins'].keys()
    }


def fullData(master):
    """
        Send the actual configuration of the builders, how the steps are agenced.
        Note that full data will never send actual detail of what command is run, name of servers, etc.
    """

    builders = []
    for b in master.config.builders:
        steps = []
        for step in b.factory.steps:
            steps.append(getName(step))
        builders.append(steps)
    return {'builders': builders}


def computeStatistics(master):
    if master.config.buildbotNetStatistics is None:
        return
    data = basicData(master)

    if master.config.buildbotNetStatistics != "basic":
        data.update(fullData(master))

    if callable(master.config.buildbotNetStatistics):
        data = master.config.buildbotNetStatistics(data)

    return data


def _sendBuildbotNetStatistics(data):
    log.msg("buildbotNetStatistics: sending {}".format(data))
    data = json.dumps(data)
    clen = len(data)
    req = urllib2.Request(PHONE_HOME_URL, data, {'Content-Type': 'application/json', 'Content-Length': clen})
    f = urllib2.urlopen(req)
    res = f.read()
    f.close()
    log.msg("buildbotNetStatistics: buildbot.net said:", res)


def sendBuildbotNetStatistics(master):
    if master.config.buildbotNetStatistics is None:
        return
    data = computeStatistics(master)
    if data is None:
        return
    threads.deferToThread(_sendBuildbotNetStatistics, data)
