#!/bin/bash

set -ex

if [[ $(id -u) != 0 ]]; then
   echo "$0 needs to be run as root" ; exit 1
fi

yum install -y http://dl.fedoraproject.org/pub/epel/7/x86_64/e/epel-release-7-9.noarch.rpm || :
yum install -y python2-pip gcc redhat-rpm-config openssl-devel python-devel

# Interim EPEL-based approach to enable testing of --ask-pass option
yum install -y sshpass

# Check the RPM can be built successfully
yum install -y tito
yum-builddep -y leapp.spec
TERM=xterm tito build --rpm --test || (echo "Failed to build leapp RPM" && exit 1)
# TODO: Actually install the built RPM & use that in the integration tests

# Configure the system to run the integration tests
yum install -y ansible

cd centos-ci/ansible/

ansible-playbook -i 'localhost,' -c local playbook.yml

Xvfb :19 -screen 0 1024x768x16 &
export DISPLAY=:19

scl enable rh-python35 sclo-vagrant1 -- sh -xc "cd ../.. && pipenv shell 'cd integration-tests && behave --no-color --junit; exit \\\$?'"
