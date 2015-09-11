#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2015, Chris Lajoie <ctlajoie@gmail.com>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
#

DOCUMENTATION = '''
---
module: ini_file
short_description: Tweak settings in INI files
extends_documentation_fragment: files
description:
     - Manage (add, remove, change) individual settings in an INI-style file without having
       to manage the file as a whole with, say, M(template) or M(assemble).
     - File is created if it does not exist. Missing sections are added.
     - Comments and blank lines are preserved in existing files.
version_added: "0.9"
options:
  dest:
    description:
      - Path to the INI-style file; this file is created if required
    required: true
    default: null
  section:
    description:
      - Section name in INI file. This is added if C(state=present) automatically when
        a single value is being set.
    required: false
    default: null
  option:
    description:
      - this is the name of the option. May be omitted if removing an entire I(section).
    required: false
    default: null
  value:
    description:
     - the string value to be associated with an I(option). May be omitted when removing an I(option).
    required: false
    default: null
  backup:
    description:
      - Create a backup file including the timestamp information so you can get
        the original file back if you somehow clobbered it incorrectly.
    required: false
    default: "no"
    choices: [ "yes", "no" ]
  others:
     description:
       - all arguments accepted by the M(file) module also work here
     required: false
  state:
     description:
       - If set to C(absent) the option or section will be removed if present instead of created.
     required: false
     default: "present"
     choices: [ "present", "absent" ]
author: "Chris Lajoie (@ctlajoie)"
'''

EXAMPLES = '''
# Ensure "fav=lemonade is in section "[drinks]" in specified file
- ini_file: dest=/etc/conf section=drinks option=fav value=lemonade mode=0600 backup=yes

- ini_file: dest=/etc/anotherconf
            section=drinks
            option=temperature
            value=cold
            backup=yes
'''

import sys
import re
import os.path


def do_ini(module, filename, section=None, option=None, value=None, state='present', backup=False):
    changed = False

    ini = IniFile(filename)

    if state == 'present':
        if option and value != ini.get_option(section, option):
            ini.set_option(section, option, value)
            changed = True

    if state == 'absent':
        if section and not option:
            #delete entire section
            changed = ini.del_section(section)
        elif option:
            #delete single option
            changed = ini.del_option(section, option)

    if changed and not module.check_mode:
        if backup:
            module.backup_local(filename)

        try:
            ini.save()
        except:
            module.fail_json(msg="Can't create %s" % filename)

    return changed


class IniFile(object):
    def __init__(self, filepath):
        self.rx_option = re.compile('^([^\s=]+)\s*=\s*(.*)')
        self.rx_section = re.compile('^\[([^\]]+)\]')
        self.filepath = filepath
        if os.path.isfile(filepath):
            f = open(filepath)
            try:
                self.lines = f.readlines()
            finally:
                f.close
        else:
            self.lines = []


    def save(self):
        f = open(filepath)
        try:
            f.writelines(self.lines)
        finally:
            f.close

    def get_option(self, section, option):
        cur_section = None
        for lineno in range(len(self.lines)):
            line = self.lines[lineno].strip()
            if len(line) == 0 or line.startswith('#') or line.startswith(';'):
                continue;

            match = self.rx_option.match(line)
            if match:
                opt, value = match.group(1, 2)
                if cur_section == section and opt == option:
                    return value
                continue

            match = self.rx_section.match(line)
            if match:
                cur_section = match.group(1)
                continue

    def set_option(self, section, option, value):
        cur_section = None
        lineno = last_opt_line = 0
        for lineno in range(len(self.lines)):
            line = self.lines[lineno].strip()
            if len(line) == 0:
                continue

            if line.startswith('#') or line.startswith(';'):
                last_opt_line = lineno
                continue

            match = self.rx_option.match(line)
            if match:
                opt = match.group(1)
                if cur_section == section and opt == option:
                    self.lines[lineno] = "%s = %s\n" % (option, value)
                    return
                last_opt_line = lineno
                continue

            match = self.rx_section.match(line)
            if match:
                #if we're about to leave the desired section, insert our option at the end of it
                if cur_section == section:
                    ins_index = last_opt_line > 0 and last_opt_line + 1 or 0
                    self.lines[ins_index:ins_index] = "%s = %s\n" % (option, value)
                    return
                cur_section = match.group(1)
                last_opt_line = lineno
                continue

        if cur_section != section:
            #the desired section doesn't exist, so add it
            if lineno > 0 and lineno - last_opt_line < 2:
                self.lines.extend("\n") #add line before section header for readability
            self.lines.extend("[%s]\n" % section)
            #and now insert the option
            self.lines.extend("%s = %s\n" % (option, value))
        else:
            #option wasn't found so we need to add it
            self.lines[last_opt_line+1:last_opt_line+1] = "%s = %s\n" % (option, value)



    def del_option(self, section, option):
        cur_section = None
        for lineno in range(len(self.lines)):
            line = self.lines[lineno].strip()
            if len(line) == 0 or line.startswith('#') or line.startswith(';'):
                continue

            match = self.rx_option.match(line)
            if match:
                opt = match.group(1)
                if cur_section == section and opt == option:
                    del self.lines[lineno]
                    return True
                continue

            match = self.rx_section.match(line)
            if match:
                cur_section = match.group(1)
                continue

        return False

    def del_section(self, section):
        section_start = None
        for lineno in range(len(self.lines)):
            line = self.lines[lineno].strip()

            match = self.rx_section.match(line)
            if match and match.group(1) == section:
                section_start = lineno
            elif match and section_start != None:
                del self.lines[section_start:lineno]
                return True

        if section_start != None:
            del self.lines[section_start:]
            return True

        return False


def main():
    module = AnsibleModule(
        argument_spec = dict(
            dest = dict(required=True),
            section = dict(required=False),
            option = dict(required=False),
            value = dict(required=False),
            backup = dict(default='no', type='bool'),
            state = dict(default='present', choices=['present', 'absent'])
        ),
        add_file_common_args = True,
        supports_check_mode = True
    )

    dest = os.path.expanduser(module.params['dest'])
    section = module.params['section']
    option = module.params['option']
    value = module.params['value']
    state = module.params['state']
    backup = module.params['backup']

    changed = do_ini(module, dest, section, option, value, state, backup)

    file_args = module.load_file_common_arguments(module.params)
    changed = module.set_fs_attributes_if_different(file_args, changed)

    # Mission complete
    module.exit_json(dest=dest, changed=changed, msg="OK")

# import module snippets
from ansible.module_utils.basic import *
if __name__ == '__main__':
    main()
