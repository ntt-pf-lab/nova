# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2011 Justin Santa Barbara
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


class IptableCommand(object):
    def __init__(self, executable, prefix, binary_name):
        self.executable = executable
        self.prefix = prefix
        self.binary_name = binary_name
        self._memento = None

    def __call__(self, name, table):
        executable, prefix = self.executable, self.prefix
        binary_name = self.binary_name
        stdout, stderr = executable('%s-save' % prefix,
                                    '-t',
                                    '%s' % name,
                                    run_as_root=True,
                                    attempts=5)
        self._memento = stdout 

        modified = _modify_rules(stdout.split('\n'), table, binary_name)
        contents = '\n'.join(modified)
        self.iptables_restore(contents)

    def rollback(self):
        assert self._memento is not None
        self.iptables_restore(self._memento)

    def iptables_restore(self, contents):
        """call restore command.
        :args:
            contents : a large string contains line-separator. not string list.
        """
        self.executable('%s-restore' % self.prefix,
                        run_as_root=True,
                        process_input=contents,
                        attempts=5)


def make_settings(ipv4, ipv6, use_ipv6):
    conf = lambda prefix, dct: [(prefix, name, table) \
                                for name, table in dct.items()]
    settings = conf('iptables', ipv4) 
    if use_ipv6:
        settings.extend(conf('ip6tables', ipv6))
    return settings


def apply(executable, settings, binary_name):
    """Modify iptable settings."""
    called = []
    try:
        for prefix, name, table in settings:
            func = IptableCommand(executable, prefix, binary_name)
            func(name, table)
            called.append(func)
        return called
    except Exception, ex:
        # rollback all.
        for x in called:
            x.rollback()
        raise ex


def _modify_rules(current_lines, table, binary_name):
    unwrapped_chains = table.unwrapped_chains
    chains = table.chains
    rules = table.rules

    # Remove any trace of our rules
    new_filter = filter(lambda line: binary_name not in line,
                        current_lines)

    seen_chains = False
    rules_index = 0
    for rules_index, rule in enumerate(new_filter):
        if not seen_chains:
            if rule.startswith(':'):
                seen_chains = True
        else:
            if not rule.startswith(':'):
                break

    our_rules = []
    for rule in rules:
        rule_str = str(rule)
        if rule.top:
            # rule.top == True means we want this rule to be at the top.
            # Further down, we weed out duplicates from the bottom of the
            # list, so here we remove the dupes ahead of time.
            new_filter = filter(lambda s: s.strip() != rule_str.strip(),
                                new_filter)
        our_rules += [rule_str]

    new_filter[rules_index:rules_index] = our_rules

    new_filter[rules_index:rules_index] = [':%s - [0:0]' % \
                                           (name,) \
                                           for name in unwrapped_chains]
    new_filter[rules_index:rules_index] = [':%s-%s - [0:0]' % \
                                           (binary_name, name,) \
                                           for name in chains]

    seen_lines = set()

    def _weed_out_duplicates(line):
        line = line.strip()
        if line in seen_lines:
            return False
        else:
            seen_lines.add(line)
            return True

    # We filter duplicates, letting the *last* occurrence take
    # precendence.
    new_filter.reverse()
    new_filter = filter(_weed_out_duplicates, new_filter)
    new_filter.reverse()
    return new_filter
