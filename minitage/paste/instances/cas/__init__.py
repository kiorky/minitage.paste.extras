# Copyright (C) 2009, Mathieu PASQUET <kiorky@cryptelium.net>
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
# 3. Neither the name of the <ORGANIZATION> nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.


__docformat__ = 'restructuredtext en'

import os
import stat
import getpass
import pwd
import grp
import re
import subprocess
import sys
import shutil


from OpenSSL.crypto import TYPE_RSA, TYPE_DSA, Error, PKey, PKeyType
from OpenSSL.crypto import X509, X509Type, X509Name, X509NameType
from OpenSSL.crypto import X509Req, X509ReqType
from OpenSSL.crypto import X509Extension, X509ExtensionType
from OpenSSL.crypto import load_certificate, load_privatekey
from OpenSSL.crypto import FILETYPE_PEM, FILETYPE_ASN1, FILETYPE_TEXT
from OpenSSL.crypto import dump_certificate, load_certificate_request
from OpenSSL.crypto import dump_certificate_request, dump_privatekey


from distutils.dir_util import copy_tree


from minitage.paste.instances import common
from minitage.core.common import remove_path, which, search_latest
from paste.script import templates

re_flags = re.M|re.U|re.I|re.S
running_user = getpass.getuser()
version = '6.0.20'

def dump_write(content, dump_path):
    f = open(dump_path, 'w')
    f.write(content)
    f.close()

class Template(common.Template):

    summary = 'Template for creating a postgresql instance'
    _template_dir = 'template'
    use_cheetah = True
    pg_present = False

    def pre(self, command, output_dir, vars):
        common.Template.pre(self, command, output_dir, vars)
        vars['running_user'] = running_user
        vars['catalina_base'] = os.path.join(
            vars['sys'],
            'var', 'data',
            'tomcat',
            'cas',
        )

    def post(self, command, output_dir, vars):
        # symlink conf, and logs directories inside $sys
        print
        print
        dirs = [os.path.join(vars['sys'], 'bin'),
                os.path.join(vars['sys'], 'etc', 'init.d')]
        for directory in dirs:
            for filep in os.listdir(directory):
                p = os.path.join(directory, filep)
                os.chmod(p, stat.S_IRGRP|stat.S_IXGRP|stat.S_IRWXU)

        # be nice, link some files
        conf = os.path.join(
            vars['sys'],
            'var', 'data',
            'tomcat',
            'cas',
            'conf'
        )
        logs = os.path.join(
            vars['sys'],
            'var', 'data',
            'tomcat',
            'cas',
            'logs'
        )
        dconf = os.path.join(
            vars['sys'],
            'etc',
            '%s.tomcat' % vars['project'],
            'cas'
        )
        dlogs = os.path.join(
            vars['sys'],
            'var',
            'log',
            'tomcat',
            'cas'
        )
        for p in dlogs, dconf:
            if os.path.exists(p):
                os.remove(p)
        os.symlink(conf, dconf)
        os.symlink(logs, dlogs)
        keysp = os.path.join(
            os.path.dirname(conf),
            'keys'
        )
        if not os.path.exists(keysp):
            os.makedirs(keysp)
        make_certificate(keysp, vars=vars)
        README = '\n\n%s' % (
            "Installation is now finished.\n"
            "------------------------------\n"
            "\n"
            " * You can find an init script to lunach your tomcat instance in %s/etc/init.d/tomcat_%s.cas.\n"
            " * Your CATALINA_BASE is installed in %s.\n"
            " * wrappers for various tomcat script have been isntalled in %s/bin.\n"
            "    * %s\n"
            " * logs are in %s/var/log/tomvat/cas\n"
            " * symlinks for the configuration directory have been made into %s/etc.\n"
            "\n" %(
                vars['sys'],
                vars['project'],
                os.path.dirname(conf),
                vars['sys'],
                ',  '.join (
                    [a
                     for a in os.listdir(os.path.join(vars['sys'], 'bin'))
                     if 'cas.' in a]
                ),
                vars['sys'],
                vars['sys'],
            )
        )

        for app in ['ROOT', 'manager', 'host-manager']:
            o = os.path.join(vars['catalina_home'], 'webapps', app)
            d = os.path.join(vars['catalina_base'], 'webapps', app)
            msg =  " * Copying %s application from %s.\n" % (app, o)
            README += msg
            copy_tree(o, d)
        if vars['inside_minitage']:
            README += '\n%s' % (
                "Please verify that tomcat-%s is in your minibuild's dependencies\n"
                "---------------------------------------------------------------------\n"
                "If not, please add it and run the following commands:\n"
                " minimerge -v tomcat-%s\n"
                " source %s/share/minitage/minitage.env\n"
                " $MT/paster create -t minitage.instances.env %s\n"
                "\n" % (version, version, vars['sys'], vars['project'])
            )
        README += '%s'% (
                "\n-------------------------------------------------------------------------------------------------------\n"
            " * It's your job to CONFIGURE CAS TO USE ANOTHER BACKEND FOR PASSWORDS !\n"
            " * CAS is installed under %s"
            "\n-------------------------------------------------------------------------------------------------------\n\n"
            ""%os.path.join(vars['catalina_base'], 'webapps', 'cas'),
        )
        readmep = os.path.join(vars['path'], 'README.tomcat.cas')
        print README
        print "Those informations have been savec in %s" % readmep
        open(readmep, 'w').write(README)

    def read_vars(self, command=None):
        vars = templates.Template.read_vars(self, command)
        for i, var in enumerate(vars[:]):
            if var.name in ['catalina_home']:
                if os.path.exists(
                    os.path.join(sys.prefix, 'etc', 'minimerge.cfg')
                ):
                    vars[i].default = os.path.join(
                        sys.prefix,
                        'dependencies',
                        'tomcat-%s' % version,
                        'parts',
                        'part'
                    )
        return vars

def set_x509(kw, xname = None):
    if not xname:
        # XXX There's no other way to get a new X509Name yet.
        xname = X509().get_subject()

    xname.countryName = kw['C']
    xname.stateOrProvinceName = kw['ST']
    xname.localityName = kw['L']
    xname.organizationName = kw['O']
    xname.organizationalUnitName = kw['OU']
    xname.emailAddress = kw['emailAddress']
    xname.commonName = kw['CN']

    return xname

def set_x509_serv(xname=None, vars = None):
    kw = {
         'C':'FR',
         'ST':'StateServ',
         'L':'NantesServ',
         'O':'OrgServ',
         'OU':'UnitServ',
         'emailAddress':'dj.coin@laposte.net',
         }
    kw['CN'] = vars.get('host', 'servcas')
    for var in kw:
        key = 'ssl_server_%s' % var
        if key in vars:
            kw[var] = vars[key]
    return set_x509(kw, xname)

def set_x509_ca(xname=None, vars = None):
    kw = {
        'C':'FR',
        'ST':'StateCA',
        'L':'TownCa',
        'O':'OrgCA',
        'OU':'UnitCA',
        'emailAddress':'foo@foo.com',
    }
    kw['CN'] = vars.get('host', 'localhost')
    for var in kw:
        key = 'ssl_ca_%s' % var
        if key in vars:
            kw[var] = vars[key]
    return set_x509(kw, xname)


def make_certificate(out_dir='/',
                     ca_crt='ca.crt',
                     ca_key='ca.key',
                     server_crt='server.crt',
                     server_key='server.key',
                     vars=None,
                    ):
    ca_key_path = os.path.join(out_dir, ca_key)
    server_key_path = os.path.join(out_dir, server_key)
    ca_crt_path = os.path.join(out_dir, ca_crt)
    server_crt_path = os.path.join(out_dir, server_crt)

    # make the certificat of CA
    # need passphrase ?
    ca_key = PKey()
    ca_key.generate_key(TYPE_RSA, 1024)
    dump_write(dump_privatekey(FILETYPE_PEM, ca_key),
               ca_key_path)

    # MAKE THE CA SELF-SIGNED CERTIFICATE
    cert =  X509()
    sub = cert.get_subject()
    set_x509_ca(sub, vars=vars)

    #FORMAT : YYYYMMDDhhmmssZ
    after =  '20200101000000Z'
    before = '20090101000000Z'
    cert.set_notAfter(after)
    cert.set_notBefore(before)

    cert.set_serial_number(1)
    cert.set_pubkey(ca_key)
    cert.set_issuer(cert.get_subject())

    cert.sign(ca_key,"MD5")
    dump_write(dump_certificate(FILETYPE_PEM, cert),
               ca_crt_path)
    print "Generated CA certificate in %s" % ca_crt_path

    # MAKE THE SERVER CERTIFICATE
    s_key = PKey()
    s_key.generate_key(TYPE_RSA, 1024)
    dump_write(dump_privatekey(FILETYPE_PEM, s_key),
               server_key_path)
    s_cert = X509()
    s_sub = s_cert.get_subject()
    set_x509_serv(s_sub, vars=vars)

    #FORMAT : YYYYMMDDhhmmssZ
    after =  '20200101000000Z'
    before = '20090101000000Z'
    s_cert.set_notAfter(after)
    s_cert.set_notBefore(before)

    s_cert.set_serial_number(2)
    s_cert.set_pubkey(s_key)
    s_cert.set_issuer(cert.get_subject())


    s_cert.sign(ca_key,"MD5")
    dump_write(dump_certificate(FILETYPE_PEM, s_cert),
               server_crt_path)
    print "Generated Server certificate in %s" % server_crt_path

Template.required_templates = ['minitage.instances.env']
gid = pwd.getpwnam(running_user)[3]
#group = grp.getgrgid(gid)[0]
Template.vars = common.Template.vars + \
        [
            templates.var('user', 'Default user',  default = 'minitageuser'),
            templates.var('catalina_home', 'Path to the tomcat install',  default = ''),
            templates.var('password', 'Default user password', default = 'secret'),
            templates.var('host', 'Host to listen on', default = 'localhost'),
            templates.var('ajp_port', 'Port to listen to for ajp connection', default = '8009'),
            templates.var('ssl_port', 'Port to listen to for ssl connection', default = '8443'),
            templates.var('tomcat_port', 'Port to listen to for tomcat', default = '8005'),
            templates.var('http_port', 'Port to listen to for http connection', default = '8080'),
            templates.var('admin_user', 'Tomcat administrator', default = running_user),
            templates.var('admin_password', 'Tomcat administrator password', default = 'secret'),
            templates.var('ssl_ca_C', 'SSL Ca Country', default = 'FR'),
            templates.var('ssl_ca_L', 'SSL Ca town', default = 'Paris'),
            templates.var('ssl_ca_ST', 'SSL Ca state', default = 'CaState'),
            templates.var('ssl_ca_O', 'SSL Ca Organization', default = 'organizationCorp'),
            templates.var('ssl_ca_OU', 'SSL Ca Unit', default = 'SpecialUnit'),
            templates.var('ssl_ca_emailAddress', 'SSL Ca email', default = '%s@localhost'%running_user),
            templates.var('ssl_server_C', 'SSL Server Country', default = 'FR'),
            templates.var('ssl_server_L', 'SSL Server town', default = 'Paris'),
            templates.var('ssl_server_ST', 'SSL Server state', default = 'ServerState'),
            templates.var('ssl_server_O', 'SSL Server Organization', default = 'organizationCorp'),
            templates.var('ssl_server_OU', 'SSL Server Unit', default = 'SpecialUnit'),
            templates.var('ssl_server_emailAddress', 'SSL Server email',
                          default = '%s@localhost' % ( running_user)
                         ),
        ]
# vim:set et sts=4 ts=4 tw=80: