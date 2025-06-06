# Three Ways to Try FreeBSD in Under Five Minutes

This directory contains scripts related to the [blog post](https://freebsdfoundation.org/blog/three-ways-to-try-freebsd-in-under-five-minutes/) and YouTube videos.

## Qemu

There's a small [wrapper script](runit.sh) for running Qemu, as mentioned in the [YouTube video]().

## Ansible

There's also a small [wrapper script](r) for running Ansible.

You should update the [Ansible inventory](inventory.yml) file for your hosts. See all the 'CHANGEME' labels.

## Terraform

The Terraform configuration assumes your AWS credentials are already configured.
[There are multiple ways to do this](https://registry.terraform.io/providers/hashicorp/aws/latest/docs#authentication-and-configuration), choose your preferred method.

By default, creates the host in AWS region eu-west-2. Depending on where you are in the world, you might like to change that. It's [on line 5](ec2.tf#L5).

You will need to set your AWS SSH key name, either on the command line (with `--var key=NAMEOFYOURSSHKEYINAWS`) or in [terraform.tfvars](terraform.tfvars).

### Running

You can do a `terraform plan` to check what will happen. Then it's just a case of:

```
$ terraform apply
$ make inventory
$ ./r
```

Take a look at [the Makefile](Makefile) to see the simple 'inventory' task. `r` just runs the Ansible [configure](configure.yml) playbook here. You might like to tune the package list in the [inventory](inventory.yml).

## Tools

In case you're interested in the tools mentioned in the video, here are some of the packages installed:

[bat](https://github.com/sharkdp/bat)
A cat(1) clone with syntax highlighting and Git integration.

[duf](https://github.com/muesli/duf)
Disk Usage/Free Utility

[dust](https://github.com/bootandy/dust)
du + rust = dust. Like du but more intuitive.

[fd](https://github.com/sharkdp/fd)
A simple, fast and user-friendly alternative to find.

[freecolor](https://freebsdsoftware.org/sysutils/freecolor.html)
Displays free memory as a bargraph

[fzf](https://github.com/junegunn/fzf)
is a general-purpose command-line fuzzy finder

[ripgrep](https://github.com/BurntSushi/ripgrep)
is line-oriented search tool that recursively searches the current directory for a regex pattern

[starship](https://starship.rs)
The minimal, blazing-fast, and infinitely customizable prompt for any shell!

[zoxide](https://github.com/ajeetdsouza/zoxide)
zoxide is a smarter cd command, inspired by z and autojump.
