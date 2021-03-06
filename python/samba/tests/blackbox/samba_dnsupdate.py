# Blackbox tests for "samba_dnsupdate" command
# Copyright (C) Kamen Mazdrashki <kamenim@samba.org> 2011
# Copyright (C) Andrew Bartlett <abartlet@samba.org> 2015
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import samba.tests
from StringIO import StringIO
from samba.netcmd.main import cmd_sambatool
from samba.credentials import Credentials
from samba.auth import system_session
from samba.samdb import SamDB
import ldb

class SambaDnsUpdateTests(samba.tests.BlackboxTestCase):
    """Blackbox test case for samba_dnsupdate."""

    def setUp(self):
        self.server_ip = samba.tests.env_get_var_value("DNS_SERVER_IP")
        super(SambaDnsUpdateTests, self).setUp()
        try:
            out = self.check_output("samba_dnsupdate --verbose")
            self.assertTrue("Looking for DNS entry" in out, out)
        except samba.tests.BlackboxProcessError:
            pass

    def test_samba_dnsupate_no_change(self):
        out = self.check_output("samba_dnsupdate --verbose")
        self.assertTrue("No DNS updates needed" in out, out)

    def test_samba_dnsupate_set_ip(self):
        try:
            out = self.check_output("samba_dnsupdate --verbose --current-ip=10.0.0.1")
            self.assertTrue(" DNS updates and" in out, out)
            self.assertTrue(" DNS deletes needed" in out, out)
        except samba.tests.BlackboxProcessError:
            pass

        try:
            out = self.check_output("samba_dnsupdate --verbose --use-nsupdate --current-ip=10.0.0.1")
        except samba.tests.BlackboxProcessError as e:
            self.fail("Error calling samba_dnsupdate: %s" % e)

        self.assertTrue("No DNS updates needed" in out, out)
        try:
            rpc_out = self.check_output("samba_dnsupdate --verbose --use-samba-tool --rpc-server-ip=%s" % self.server_ip)
        except samba.tests.BlackboxProcessError as e:
            self.fail("Error calling samba_dnsupdate: %s" % e)

        self.assertTrue(" DNS updates and" in rpc_out, rpc_out)
        self.assertTrue(" DNS deletes needed" in rpc_out, rpc_out)
        out = self.check_output("samba_dnsupdate --verbose")
        self.assertTrue("No DNS updates needed" in out, out + rpc_out)

    def test_add_new_uncovered_site(self):
        name = 'sites'
        cmd = cmd_sambatool.subcommands[name]
        cmd.outf = StringIO()
        cmd.errf = StringIO()

        site_name = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'

        # Clear out any existing site
        cmd._run("samba-tool %s" % name, 'remove', site_name)

        result = cmd._run("samba-tool %s" % name, 'create', site_name)
        if result is not None:
            self.fail("Error creating new site")

        self.lp = samba.tests.env_loadparm()
        self.creds = Credentials()
        self.creds.guess(self.lp)
        self.session = system_session()

        self.samdb = SamDB(session_info=self.session,
                           credentials=self.creds,
                           lp=self.lp)

        m = ldb.Message()
        m.dn = ldb.Dn(self.samdb, 'CN=DEFAULTIPSITELINK,CN=IP,'
                      'CN=Inter-Site Transports,CN=Sites,{}'.format(
                          self.samdb.get_config_basedn()))
        m['siteList'] = ldb.MessageElement("CN={},CN=Sites,{}".format(
            site_name,
            self.samdb.get_config_basedn()),
            ldb.FLAG_MOD_ADD, "siteList")

        out = self.check_output("samba_dnsupdate --verbose")
        self.assertTrue("No DNS updates needed" in out, out)

        self.samdb.modify(m)

        out = self.check_output("samba_dnsupdate --verbose --use-samba-tool"
                                " --rpc-server-ip={}".format(self.server_ip))

        self.assertFalse("No DNS updates needed" in out, out)
        self.assertTrue(site_name.lower() in out, out)

        result = cmd._run("samba-tool %s" % name, 'remove', site_name)
        if result is not None:
            self.fail("Error deleting site")
