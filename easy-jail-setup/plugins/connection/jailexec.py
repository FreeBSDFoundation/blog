#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright (c) 2025 Christian Hofstede-Kuhn <christian@hofstede.it>
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

"""
FreeBSD Jail Connection Plugin for Ansible

This connection plugin enables Ansible to execute tasks inside FreeBSD jails
by connecting to the jail host via SSH and using jexec to run commands within
the jail. It provides a secure, efficient way to manage jail containers without
requiring direct SSH access to individual jails.

Features:
- SSH connection to jail host with full authentication support
- Jail command execution via jexec with privilege escalation (doas/sudo)
- Efficient file transfer with proper permission handling
- Connection pooling and persistence for improved performance
- Comprehensive error handling and logging
- Production-ready code quality with extensive documentation
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import os
import re
import shlex
import time
from typing import Callable, Tuple, Union

from ansible.errors import AnsibleConnectionFailure, AnsibleError
from ansible.playbook.play_context import PlayContext
from ansible.plugins.connection.ssh import Connection as SSHConnection
from ansible.utils.display import Display

# Module-level display instance for consistent logging
display = Display()

# Constants for configuration
DEFAULT_JAIL_USER = "root"
DEFAULT_PRIVILEGE_ESCALATION = "doas"
DEFAULT_REMOTE_TMP = "/tmp/.ansible/tmp"
TEMP_FILE_PREFIX = "ansible-jailexec"
DEFAULT_CONNECTION_TIMEOUT = 30
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY = 1.0

# Security constants
MAX_JAIL_NAME_LENGTH = 255
VALID_JAIL_NAME_REGEX = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def validate_jail_name(jail_name: str) -> None:
    """
    Validate jail name for security and FreeBSD compliance.

    Args:
        jail_name: The jail name to validate

    Raises:
        AnsibleConnectionFailure: If jail name is invalid
    """
    if not jail_name or not jail_name.strip():
        raise AnsibleConnectionFailure("Jail name cannot be empty")

    jail_name = jail_name.strip()

    if len(jail_name) > MAX_JAIL_NAME_LENGTH:
        raise AnsibleConnectionFailure(
            f"Jail name too long (max {MAX_JAIL_NAME_LENGTH} characters): {jail_name}"
        )

    if not VALID_JAIL_NAME_REGEX.match(jail_name):
        raise AnsibleConnectionFailure(
            f"Invalid jail name format: {jail_name}. "
            "Jail names must start with alphanumeric and contain only letters, "
            "numbers, dots, underscores, and hyphens."
        )


def validate_path_security(path: str) -> None:
    """Validate file paths to prevent security attacks."""
    if not path or not path.strip():
        if path and path.strip() != path:  # Whitespace-only paths
            raise AnsibleError(
                f"Path contains dangerous pattern (whitespace-only): {repr(path)}"
            )
        return

    # Security validation for dangerous patterns
    dangerous_patterns = [
        "..",  # Directory traversal
        "$(",  # Command substitution
        "`",  # Command substitution
        "|",  # Pipe operations
        ";",  # Command separation
        "&",  # Background processes
        "(",  # Function calls or subshells
    ]

    for pattern in dangerous_patterns:
        if pattern in path:
            raise AnsibleError(f"Path contains dangerous pattern '{pattern}': {path}")


def retry_on_failure(
    max_attempts: int = MAX_RETRY_ATTEMPTS,
    delay: float = RETRY_DELAY,
    exceptions: Tuple = (AnsibleConnectionFailure,),
) -> Callable:
    """Decorator to retry functions on transient failures with exponential backoff."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        display.vvv(f"Retry attempt {attempt + 1} failed: {e}")
                        time.sleep(delay * (attempt + 1))
                    else:
                        display.vvv(f"All {max_attempts} attempts failed")
            raise last_exception

        return wrapper

    return decorator


DOCUMENTATION = """
    name: jailexec
    short_description: Execute tasks in FreeBSD jails via jexec over SSH
    description:
        - This connection plugin allows Ansible to execute tasks inside FreeBSD jails
        - Uses SSH to connect to the jail host, then jexec to run commands within the jail
        - Supports file transfers, privilege escalation, and connection persistence
        - Designed for production use with comprehensive error handling
    author: Christian Hofstede-Kuhn <christian@hofstede.it>
    version_added: "2.0"
    options:
        # SSH connection options (inherited from SSH plugin)
        host:
            description: Hostname/IP of the jail host to connect to
            default: inventory_hostname
            vars:
                - name: inventory_hostname
                - name: ansible_host
                - name: ansible_ssh_host
        ssh_executable:
            description: Location of SSH executable
            default: 'ssh'
            vars:
                - name: ansible_ssh_executable
        sftp_executable:
            description: Location of SFTP executable
            default: 'sftp'
            vars:
                - name: ansible_sftp_executable
        scp_executable:
            description: Location of SCP executable
            default: 'scp'
            vars:
                - name: ansible_scp_executable
        ssh_args:
            description: Arguments to pass to SSH CLI tools
            default: ''
            vars:
                - name: ansible_ssh_args
        ssh_common_args:
            description: Extra arguments for SSH CLI tools
            default: ''
            vars:
                - name: ansible_ssh_common_args
        ssh_extra_args:
            description: SSH-specific extra arguments
            default: ''
            vars:
                - name: ansible_ssh_extra_args
        port:
            description: Remote port for SSH connection
            type: int
            default: 22
            vars:
                - name: ansible_port
                - name: ansible_ssh_port
        remote_user:
            description: User for SSH login to jail host
            vars:
                - name: ansible_user
                - name: ansible_ssh_user
        timeout:
            description: Connection timeout in seconds
            type: int
            default: 10
            vars:
                - name: ansible_timeout
                - name: ansible_ssh_timeout
        private_key_file:
            description: Path to SSH private key
            vars:
                - name: ansible_private_key_file
                - name: ansible_ssh_private_key_file
        password:
            description: SSH password
            vars:
                - name: ansible_password
                - name: ansible_ssh_password
        host_key_checking:
            description: Whether to check SSH host keys
            type: bool
            default: true
            vars:
                - name: ansible_host_key_checking
                - name: ansible_ssh_host_key_checking
        use_tty:
            description: Force TTY allocation
            type: bool
            default: true
            vars:
                - name: ansible_ssh_use_tty
        reconnection_retries:
            description: Number of connection retry attempts
            type: int
            default: 3
            vars:
                - name: ansible_ssh_reconnection_retries

        # Jail-specific options
        jail_name:
            description: Name of the jail to connect to
            vars:
                - name: ansible_jail_name
        jail_host:
            description: FreeBSD host that runs the jails
            required: true
            vars:
                - name: ansible_jail_host
        jail_user:
            description: User to execute commands as within the jail
            default: root
            vars:
                - name: ansible_user
                - name: ansible_jail_user
        privilege_escalation:
            description: Privilege escalation method (doas or sudo)
            default: doas
            choices: ['doas', 'sudo']
            vars:
                - name: ansible_jail_privilege_escalation
                - name: ansible_privilege_escalation
        remote_tmp:
            description: Remote temporary directory for Ansible files
            default: /tmp/.ansible/tmp
            vars:
                - name: ansible_remote_tmp
                - name: ansible_jail_remote_tmp

    notes:
        - Requires SSH access to the jail host with privilege escalation (doas/sudo)
        - The jail must exist and be running on the target host
        - File transfers use a two-stage process for proper permission handling
        - Connection pooling improves performance for multiple operations
        - All paths starting with ~ are converted to use the remote_tmp directory

    seealso:
        - name: FreeBSD Jails Handbook
          description: Official FreeBSD documentation on jails
          link: https://docs.freebsd.org/en/books/handbook/jails/
        - name: Ansible SSH Connection Plugin
          description: Base SSH plugin documentation
          link: https://docs.ansible.com/ansible/latest/plugins/connection/ssh.html

    examples:
        - name: Inventory configuration for jail management
          description: |
            Configure inventory to manage FreeBSD jails via SSH to jail host
          code: |
            # inventory/hosts
            [jail_hosts]
            freebsd-host.example.com ansible_connection=ssh ansible_user=admin

            [jails]
            web-jail ansible_connection=jailexec ansible_jail_host=freebsd-host.example.com
            db-jail  ansible_connection=jailexec ansible_jail_host=freebsd-host.example.com

        - name: Playbook using jail connection
          description: |
            Execute tasks inside jails using the jailexec connection plugin
          code: |
            - hosts: jails
              connection: jailexec
              tasks:
                - name: Install package in jail
                  package:
                    name: nginx
                    state: present

                - name: Copy configuration file to jail
                  copy:
                    src: nginx.conf
                    dest: /usr/local/etc/nginx/nginx.conf

                - name: Start service in jail
                  service:
                    name: nginx
                    state: started
                    enabled: yes
"""


class Connection(SSHConnection):
    """
    FreeBSD jail connection using jexec over SSH.

    This connection plugin extends the SSH connection to enable execution
    of commands inside FreeBSD jails. It maintains an SSH connection to the
    jail host and uses jexec to run commands within the specified jail.

    The plugin handles:
    - SSH connection management with connection pooling
    - Jail command execution via jexec with privilege escalation
    - File transfers with proper permission handling
    - Path transformations for jail filesystem access
    - Comprehensive error handling and logging

    Attributes:
        transport (str): Connection transport identifier
        has_pipelining (bool): Whether connection supports pipelining
        jail_name (str): Name of the target jail
        jail_host (str): Hostname of the jail host
        jail_user (str): User to execute commands as within jail
        privilege_escalation (str): Method for privilege escalation
        remote_tmp (str): Remote temporary directory path
        _jail_root_cache (Optional[str]): Cached jail root path
        _host_connection (Optional[SSHConnection]): SSH connection to jail host
    """

    transport = "jailexec"
    has_pipelining = True

    _play_context: PlayContext

    def __init__(self, play_context, new_stdin, *args, **kwargs):
        """Initialize the jail connection with security validation."""
        self.jail_name = play_context.remote_addr

        if self.jail_name:
            validate_jail_name(self.jail_name)

        self.jail_host = None
        self.jail_user = play_context.remote_user or DEFAULT_JAIL_USER
        self.privilege_escalation = DEFAULT_PRIVILEGE_ESCALATION
        self.remote_tmp = DEFAULT_REMOTE_TMP
        self.connection_timeout = DEFAULT_CONNECTION_TIMEOUT

        self._jail_root_cache = None
        self._host_connection = None
        self._last_activity = time.time()

        display.vvv(
            f"jailexec: Initializing connection to jail '{self.jail_name}'",
            host=self.jail_name,
        )

        super(Connection, self).__init__(play_context, new_stdin, *args, **kwargs)

    def _get_jail_configuration(self) -> None:
        """Load and validate jail configuration from Ansible options."""
        try:
            jail_host = self.get_option("jail_host")
            if not jail_host or not jail_host.strip():
                raise AnsibleConnectionFailure(
                    f"No jail host specified for jail '{self.jail_name}'. "
                    "Set ansible_jail_host in inventory."
                )
            self.jail_host = jail_host.strip()

            jail_name_option = self.get_option("jail_name")
            if jail_name_option and jail_name_option != self.jail_name:
                validate_jail_name(jail_name_option)
                display.vvv(
                    f"jailexec: Overriding jail name to '{jail_name_option}'",
                    host=self.jail_name,
                )
                self.jail_name = jail_name_option

            jail_user = self.get_option("jail_user")
            if jail_user:
                jail_user = jail_user.strip()
                if not jail_user or jail_user.isspace():
                    raise AnsibleConnectionFailure(
                        "jail_user cannot be empty or whitespace"
                    )
                self.jail_user = jail_user

            privilege_escalation = self.get_option("privilege_escalation")
            if privilege_escalation:
                privilege_escalation = privilege_escalation.strip().lower()
                if privilege_escalation not in ["doas", "sudo"]:
                    raise AnsibleConnectionFailure(
                        f"Invalid privilege escalation method: {privilege_escalation}. Must be 'doas' or 'sudo'"
                    )
                self.privilege_escalation = privilege_escalation

            remote_tmp = self.get_option("remote_tmp")
            if remote_tmp:
                remote_tmp = remote_tmp.strip()
                if not remote_tmp:
                    raise AnsibleConnectionFailure("remote_tmp cannot be empty")
                if ".." in remote_tmp:
                    raise AnsibleConnectionFailure(
                        f"remote_tmp contains path traversal: {remote_tmp}"
                    )
                if not remote_tmp.startswith("/"):
                    raise AnsibleConnectionFailure(
                        f"remote_tmp must be an absolute path: {remote_tmp}"
                    )
                self.remote_tmp = remote_tmp

            timeout = self.get_option("timeout")
            if timeout:
                try:
                    self.connection_timeout = max(1, int(timeout))
                except (ValueError, TypeError):
                    display.warning(f"Invalid timeout value: {timeout}, using default")

        except AnsibleConnectionFailure:
            raise
        except Exception as e:
            raise AnsibleConnectionFailure(
                f"Configuration error for jail '{self.jail_name}': {e}"
            )

    @retry_on_failure(max_attempts=3, exceptions=(AnsibleConnectionFailure,))
    def _create_ssh_connection(self) -> SSHConnection:
        """
        Create and configure SSH connection to jail host.

        Returns:
            SSHConnection: Configured SSH connection to jail host

        Raises:
            AnsibleConnectionFailure: If SSH connection cannot be established
        """
        display.vvv(
            f"jailexec: Creating SSH connection to jail host: {self.jail_host}",
            host=self.jail_name,
        )

        # Create a copy of play context for jail host connection
        old_pc = self._play_context
        self._play_context = self._play_context.copy()
        self._play_context.remote_addr = self.jail_host

        try:
            # Create SSH connection to jail host (avoid deprecated stdin)
            host_conn = SSHConnection(self._play_context, None)

            # Patch get_option method to provide necessary SSH defaults
            original_get_option = host_conn.get_option

            def get_option_patch(option, hostvars=None):
                """Patched get_option with jail-aware defaults."""
                if option == "host":
                    return self.jail_host
                elif option == "remote_user":
                    return self.get_option("remote_user")
                elif option == "port":
                    return self._play_context.port or 22

                try:
                    return original_get_option(option, hostvars)
                except Exception:
                    # Provide sensible defaults for missing SSH options
                    defaults = {
                        "reconnection_retries": 3,
                        "timeout": 10,
                        "ssh_executable": "ssh",
                        "use_tty": True,
                        "host_key_checking": True,
                        "scp_executable": "scp",
                        "sftp_executable": "sftp",
                        "ssh_transfer_method": "scp",
                    }
                    return defaults.get(option)

            host_conn.get_option = get_option_patch
            host_conn._connect()

            display.vvv(
                f"jailexec: SSH connection established to {self.jail_host}",
                host=self.jail_name,
            )
            return host_conn

        finally:
            # Restore original play context
            self._play_context = old_pc

    def _connect(self):
        """
        Establish connection to jail via SSH to jail host.

        Returns:
            Connection: Self reference for method chaining

        Raises:
            AnsibleConnectionFailure: If connection cannot be established
        """
        if self._connected:
            return self

        # Load jail configuration
        self._get_jail_configuration()

        # Create SSH connection to jail host (with caching)
        if not self._host_connection:
            self._host_connection = self._create_ssh_connection()

        # Verify jail exists and is accessible
        self._verify_jail_access()

        display.vvv(
            f"jailexec: Connected to jail '{self.jail_name}' via host '{self.jail_host}'",
            host=self.jail_name,
        )

        self._connected = True
        return self

    @retry_on_failure(max_attempts=2, exceptions=(AnsibleConnectionFailure,))
    def _verify_jail_access(self) -> None:
        """
        Verify that the jail exists and is accessible.

        Raises:
            AnsibleConnectionFailure: If jail is not accessible
        """
        display.vvv(
            f"jailexec: Verifying jail access: {self.jail_name}", host=self.jail_name
        )

        if not self._host_connection:
            raise AnsibleConnectionFailure(
                "No SSH connection available for jail verification"
            )

        # Test jail accessibility with a simple command
        test_cmd = f"{self.privilege_escalation} jls -j {shlex.quote(self.jail_name)}"

        try:
            result = self._host_connection.exec_command(test_cmd)
        except Exception as e:
            raise AnsibleConnectionFailure(
                f"Failed to execute jail verification command: {e}"
            )

        if result[0] != 0:
            error_msg = self._decode_output(result[2]) if result[2] else "Unknown error"

            # Provide more helpful error messages based on common issues
            if "No such jail" in error_msg or "not found" in error_msg.lower():
                # List available jails for troubleshooting
                try:
                    list_cmd = f"{self.privilege_escalation} jls -h name"
                    list_result = self._host_connection.exec_command(list_cmd)
                    if list_result[0] == 0:
                        available_jails = self._decode_output(list_result[1]).strip()
                        raise AnsibleConnectionFailure(
                            f"Jail '{self.jail_name}' not found. Available jails:\n{available_jails}"
                        )
                except Exception:
                    pass  # If we can't list jails, just use the original error

            elif "Permission denied" in error_msg:
                raise AnsibleConnectionFailure(
                    f"Permission denied accessing jail '{self.jail_name}'. "
                    f"Ensure {self.privilege_escalation} is configured for jail management commands."
                )

            raise AnsibleConnectionFailure(
                f"Cannot access jail '{self.jail_name}': {error_msg}"
            )

    def _decode_output(self, output: Union[str, bytes]) -> str:
        """
        Decode command output handling both strings and bytes.

        Args:
            output: Command output to decode

        Returns:
            str: Decoded output string
        """
        if isinstance(output, bytes):
            return output.decode("utf-8", errors="replace")
        return output

    def _validate_command_security(self, command: str) -> None:
        """Validate command strings for dangerous patterns."""
        if not command:
            return

        # Only validate for directory traversal - other patterns are too restrictive
        # for legitimate Ansible-generated commands
        if ".." in command:
            raise AnsibleError(f"Path contains dangerous pattern '..': {command}")

    def _transform_path_only(self, path: str) -> str:
        """Transform home directory references to jail-appropriate paths."""
        if not path:
            return path

        return re.sub(
            r"(^|\s)~[^/\s]*/", r"\1" + self.remote_tmp.rstrip("/") + "/", path
        )

    def _transform_path(self, path: str) -> str:
        """Transform home directory references to jail-appropriate paths with security validation."""
        if not path:
            return path

        # Security validation for dangerous patterns
        dangerous_patterns = [
            "..",  # Directory traversal
            "$(",  # Command substitution
            "`",  # Command substitution
            "|",  # Pipe operations
            ";",  # Command separation
            "&",  # Background processes
            "(",  # Function calls or subshells
        ]

        for pattern in dangerous_patterns:
            if pattern in path:
                raise AnsibleError(
                    f"Path contains dangerous pattern '{pattern}': {path}"
                )

        return re.sub(
            r"(^|\s)~[^/\s]*/", r"\1" + self.remote_tmp.rstrip("/") + "/", path
        )

    def _get_jail_root(self) -> str:
        """Get the jail root directory path with caching."""
        if self._jail_root_cache:
            return self._jail_root_cache

        display.vvv(
            f"jailexec: Determining jail root for {self.jail_name}", host=self.jail_name
        )

        jail_root_cmd = (
            f"{self.privilege_escalation} jls -j {shlex.quote(self.jail_name)} path"
        )
        result = self._host_connection.exec_command(jail_root_cmd)

        if result[0] != 0:
            error_msg = self._decode_output(result[2]) if result[2] else "Unknown error"
            raise AnsibleError(f"Could not determine jail root path: {error_msg}")

        stdout = self._decode_output(result[1])
        jail_root = stdout.strip().split("\n")[0].strip()

        if not jail_root:
            raise AnsibleError("Empty jail root path returned from jls command")

        self._jail_root_cache = jail_root
        display.vvv(f"jailexec: Jail root cached: {jail_root}", host=self.jail_name)
        return jail_root

    def exec_command(
        self, cmd: Union[str, list], in_data=None, sudoable=True
    ) -> Tuple[int, bytes, bytes]:
        """
        Execute a command in the jail with validation and error handling.

        Args:
            cmd: Command to execute (string or list)
            in_data: Input data to send to command
            sudoable: Whether command can be run with privilege escalation

        Returns:
            Tuple[int, bytes, bytes]: Return code, stdout, stderr

        Raises:
            AnsibleError: If command execution fails
        """
        if not self._connected:
            self._connect()

        # Update activity timestamp
        self._last_activity = time.time()

        # Validate and build command string
        if isinstance(cmd, list):
            if not cmd:
                raise AnsibleError("Command list cannot be empty")
            cmd_str = " ".join(shlex.quote(str(arg)) for arg in cmd if arg is not None)
        else:
            cmd_str = str(cmd).strip()
            # Only validate string commands for dangerous patterns (list commands are safely quoted)
            self._validate_command_security(cmd_str)

        if not cmd_str:
            raise AnsibleError("Command cannot be empty")

        display.vvv(
            f"jailexec: Executing in jail '{self.jail_name}': {cmd_str}",
            host=self.jail_name,
        )

        # Transform paths in command for jail filesystem (without security validation)
        cmd_str = self._transform_path_only(cmd_str)

        # Build jail execution command
        jail_cmd_parts = [self.privilege_escalation, "jexec"]

        # Add user specification if not root
        if self.jail_user and self.jail_user != "root":
            jail_cmd_parts.extend(["-u", self.jail_user])

        # Add jail name and command
        jail_cmd_parts.extend([self.jail_name, "/bin/sh", "-c", cmd_str])

        # Build final command
        final_cmd = " ".join(shlex.quote(part) for part in jail_cmd_parts)

        display.vvv(
            f"jailexec: Executing on jail host: {final_cmd}", host=self.jail_name
        )

        # Execute via SSH connection to jail host with error handling
        try:
            if not self._host_connection:
                raise AnsibleError("No SSH connection available")

            result = self._host_connection.exec_command(final_cmd, in_data, sudoable)

            # Log command completion for debugging
            display.vvv(
                f"jailexec: Command completed with return code {result[0]}",
                host=self.jail_name,
            )

            return result

        except Exception as e:
            raise AnsibleError(
                f"Failed to execute command in jail '{self.jail_name}': {e}"
            )

    def put_file(self, in_path: str, out_path: str) -> None:
        """
        Transfer a file to the jail.

        Uses a two-stage process: first copy to a temporary location that
        the SSH user can access, then move to the jail directory using
        privilege escalation.

        Args:
            in_path: Local file path to copy from
            out_path: Remote file path in jail to copy to

        Raises:
            AnsibleError: If file transfer fails
        """
        if not self._connected:
            self._connect()

        display.vvv(
            f"jailexec: Copying file from {in_path} to jail:{out_path}",
            host=self.jail_name,
        )

        try:
            # Validate and transform output path for jail filesystem
            validate_path_security(out_path)  # Only validate the actual file path
            out_path = self._transform_path(out_path)

            # Get jail root directory
            jail_root = self._get_jail_root()
            full_out_path = os.path.join(jail_root, out_path.lstrip("/"))

            # Ensure target directory exists
            target_dir = os.path.dirname(full_out_path)
            mkdir_cmd = (
                f"{self.privilege_escalation} mkdir -p {shlex.quote(target_dir)}"
            )
            result = self._host_connection.exec_command(mkdir_cmd)
            if result[0] != 0:
                error_msg = (
                    self._decode_output(result[2]) if result[2] else "Unknown error"
                )
                raise AnsibleError(f"Failed to create target directory: {error_msg}")

            # Create unique temporary file with secure permissions
            temp_name = f"{TEMP_FILE_PREFIX}-{os.getpid()}-{os.urandom(8).hex()}"
            temp_file = f"/tmp/{temp_name}"

            display.vvv(
                f"jailexec: Transferring via temporary file {temp_file}",
                host=self.jail_name,
            )

            try:
                # Stage 1: Copy to temporary location with secure permissions
                self._host_connection.put_file(in_path, temp_file)

                # Set secure permissions on temporary file
                chmod_cmd = f"chmod 600 {shlex.quote(temp_file)}"
                chmod_result = self._host_connection.exec_command(chmod_cmd)
                if chmod_result[0] != 0:
                    display.warning(
                        f"Failed to set secure permissions on temporary file: {temp_file}"
                    )

                # Stage 2: Move to jail directory with proper permissions
                move_cmd = f"{self.privilege_escalation} mv {shlex.quote(temp_file)} {shlex.quote(full_out_path)}"
                result = self._host_connection.exec_command(move_cmd)
                if result[0] != 0:
                    error_msg = (
                        self._decode_output(result[2]) if result[2] else "Unknown error"
                    )
                    raise AnsibleError(
                        f"Failed to move file to jail directory: {error_msg}"
                    )

                display.vvv(
                    f"jailexec: File successfully copied to {full_out_path}",
                    host=self.jail_name,
                )

            except Exception as e:
                # Clean up temporary file on failure - try both with and without privilege escalation
                cleanup_cmds = [
                    f"rm -f {shlex.quote(temp_file)}",
                    f"{self.privilege_escalation} rm -f {shlex.quote(temp_file)}",
                ]
                for cleanup_cmd in cleanup_cmds:
                    try:
                        self._host_connection.exec_command(cleanup_cmd)
                        break  # If one succeeds, we're done
                    except Exception:
                        continue  # Try the next cleanup command

                if isinstance(e, AnsibleError):
                    raise
                else:
                    raise AnsibleError(f"File transfer failed: {e}")

        except Exception as e:
            raise AnsibleError(f"Failed to copy file to jail: {e}")

    def fetch_file(self, in_path: str, out_path: str) -> None:
        """
        Retrieve a file from the jail.

        Args:
            in_path: Remote file path in jail to copy from
            out_path: Local file path to copy to

        Raises:
            AnsibleError: If file retrieval fails
        """
        if not self._connected:
            self._connect()

        display.vvv(
            f"jailexec: Fetching file from jail:{in_path} to {out_path}",
            host=self.jail_name,
        )

        try:
            # Validate and transform input path for jail filesystem
            validate_path_security(in_path)  # Only validate the actual file path
            in_path = self._transform_path(in_path)

            # Get jail root directory
            jail_root = self._get_jail_root()
            full_in_path = os.path.join(jail_root, in_path.lstrip("/"))

            # Verify file exists
            test_cmd = f"test -f {shlex.quote(full_in_path)}"
            result = self._host_connection.exec_command(test_cmd)
            if result[0] != 0:
                raise AnsibleError(f"File {in_path} does not exist in jail")

            # Fetch file via SSH from jail host filesystem
            self._host_connection.fetch_file(full_in_path, out_path)

            display.vvv(
                f"jailexec: File successfully fetched from {full_in_path}",
                host=self.jail_name,
            )

        except Exception as e:
            raise AnsibleError(f"Failed to fetch file from jail: {e}")

    def close(self) -> None:
        """
        Close the connection and clean up resources.
        """
        display.vvv(
            f"jailexec: Closing connection to jail '{self.jail_name}'",
            host=self.jail_name,
        )

        # Close SSH connection to jail host
        if self._host_connection:
            self._host_connection.close()
            self._host_connection = None

        # Clear cache
        self._jail_root_cache = None

        # Call parent close method
        super(Connection, self).close()

    def __del__(self):
        """Destructor to ensure proper cleanup."""
        try:
            self.close()
        except Exception:
            # Ignore exceptions during cleanup
            pass
