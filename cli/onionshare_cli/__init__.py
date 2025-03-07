# -*- coding: utf-8 -*-
"""
OnionShare | https://onionshare.org/

Copyright (C) 2014-2022 Micah Lee, et al. <micah@micahflee.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import os
import sys
import time
import argparse
import threading
from datetime import datetime
from datetime import timedelta

from .common import Common, CannotFindTor
from .web import Web
from .onion import TorErrorProtocolError, TorTooOldEphemeral, TorTooOldStealth, Onion
from .onionshare import OnionShare
from .mode_settings import ModeSettings
from qrcode import QRCode

def main(cwd=None):
    """
    The main() function implements all of the logic that the command-line version of
    onionshare uses.
    """
    common = Common()
    common.display_banner()

    # OnionShare CLI in OSX needs to change current working directory (#132)
    if common.platform == "Darwin":
        if cwd:
            os.chdir(cwd)

    # Parse arguments
    parser = argparse.ArgumentParser(
        formatter_class=lambda prog: argparse.HelpFormatter(prog, max_help_position=28)
    )
    # Select modes
    parser.add_argument(
        "--receive", action="store_true", dest="receive", help="Receive files"
    )
    parser.add_argument(
        "--website", action="store_true", dest="website", help="Publish website"
    )
    parser.add_argument(
        "--chat", action="store_true", dest="chat", help="Start chat server"
    )
    # Tor connection-related args
    parser.add_argument(
        "--local-only",
        action="store_true",
        dest="local_only",
        default=False,
        help="Don't use Tor (only for development)",
    )
    parser.add_argument(
        "--connect-timeout",
        metavar="SECONDS",
        dest="connect_timeout",
        default=120,
        help="Give up connecting to Tor after a given amount of seconds (default: 120)",
    )
    parser.add_argument(
        "--config",
        metavar="FILENAME",
        default=None,
        help="Filename of custom global settings",
    )
    # Persistent file
    parser.add_argument(
        "--persistent",
        metavar="FILENAME",
        default=None,
        help="Filename of persistent session",
    )
    # General args
    parser.add_argument("--title", metavar="TITLE", default=None, help="Set a title")
    parser.add_argument(
        "--public",
        action="store_true",
        dest="public",
        default=False,
        help="Don't use a private key",
    )
    parser.add_argument(
        "--auto-start-timer",
        metavar="SECONDS",
        dest="autostart_timer",
        default=0,
        help="Start onion service at scheduled time (N seconds from now)",
    )
    parser.add_argument(
        "--auto-stop-timer",
        metavar="SECONDS",
        dest="autostop_timer",
        default=0,
        help="Stop onion service at schedule time (N seconds from now)",
    )
    # Share args
    parser.add_argument(
        "--no-autostop-sharing",
        action="store_true",
        dest="no_autostop_sharing",
        default=False,
        help="Share files: Continue sharing after files have been sent (default is to stop sharing)",
    )
    parser.add_argument(
        "--log-filenames",
        action="store_true",
        dest="log_filenames",
        default=False,
        help="Log file download activity to stdout"
    )
    parser.add_argument(
        "--qr",
        action="store_true",
        dest="qr",
        default=False,
        help="Display a QR code in the terminal for share links",
    )
    # Receive args
    parser.add_argument(
        "--data-dir",
        metavar="data_dir",
        default=None,
        help="Receive files: Save files received to this directory",
    )
    parser.add_argument(
        "--webhook-url",
        metavar="webhook_url",
        default=None,
        help="Receive files: URL to receive webhook notifications",
    )
    parser.add_argument(
        "--disable-text",
        action="store_true",
        dest="disable_text",
        help="Receive files: Disable receiving text messages",
    )
    parser.add_argument(
        "--disable-files",
        action="store_true",
        dest="disable_files",
        help="Receive files: Disable receiving files",
    )
    # Website args
    parser.add_argument(
        "--disable_csp",
        action="store_true",
        dest="disable_csp",
        default=False,
        help="Publish website: Disable the default Content Security Policy header (allows your website to use third-party resources)",
    )
    parser.add_argument(
        "--custom_csp",
        metavar="custom_csp",
        default=None,
        help="Publish website: Set a custom Content Security Policy header",
    )
    # Other
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        dest="verbose",
        help="Log OnionShare errors to stdout, and web errors to disk",
    )
    parser.add_argument(
        "filename",
        metavar="filename",
        nargs="*",
        help="List of files or folders to share",
    )
    args = parser.parse_args()

    filenames = args.filename
    for i in range(len(filenames)):
        filenames[i] = os.path.abspath(filenames[i])

    receive = bool(args.receive)
    website = bool(args.website)
    chat = bool(args.chat)
    local_only = bool(args.local_only)
    connect_timeout = int(args.connect_timeout)
    config_filename = args.config
    persistent_filename = args.persistent
    title = args.title
    public = bool(args.public)
    autostart_timer = int(args.autostart_timer)
    autostop_timer = int(args.autostop_timer)
    autostop_sharing = not bool(args.no_autostop_sharing)
    print_qr = bool(args.qr)
    data_dir = args.data_dir
    webhook_url = args.webhook_url
    disable_text = args.disable_text
    disable_files = args.disable_files
    disable_csp = bool(args.disable_csp)
    custom_csp = args.custom_csp
    log_filenames = bool(args.log_filenames)
    verbose = bool(args.verbose)

    # Verbose mode?
    common.verbose = verbose

    # Re-load settings, if a custom config was passed in
    if config_filename:
        common.load_settings(config_filename)
    else:
        common.load_settings()

    # Mode settings
    if persistent_filename:
        mode_settings = ModeSettings(common, persistent_filename)
        mode_settings.set("persistent", "enabled", True)
    else:
        mode_settings = ModeSettings(common)

    if receive:
        mode = "receive"
    elif website:
        mode = "website"
    elif chat:
        mode = "chat"
    else:
        mode = "share"

    if mode_settings.just_created:
        # This means the mode settings were just created, not loaded from disk
        mode_settings.set("general", "title", title)
        mode_settings.set("general", "public", public)
        mode_settings.set("general", "autostart_timer", autostart_timer)
        mode_settings.set("general", "autostop_timer", autostop_timer)
        mode_settings.set("general", "qr", print_qr)
        if persistent_filename:
            mode_settings.set("persistent", "mode", mode)
        if mode == "share":
            mode_settings.set("share", "autostop_sharing", autostop_sharing)
            mode_settings.set("share", "log_filenames", log_filenames)
        if mode == "receive":
            if data_dir:
                mode_settings.set("receive", "data_dir", data_dir)
            if webhook_url:
                mode_settings.set("receive", "webhook_url", webhook_url)
            mode_settings.set("receive", "disable_text", disable_text)
            mode_settings.set("receive", "disable_files", disable_files)
        if mode == "website":
            if disable_csp and custom_csp:
                print("You cannot disable the CSP and set a custom one. Either set --disable-csp or --custom-csp but not both.")
                sys.exit()
            if disable_csp:
                mode_settings.set("website", "disable_csp", True)
                mode_settings.set("website", "custom_csp", None)
            if custom_csp:
                mode_settings.set("website", "custom_csp", custom_csp)
                mode_settings.set("website", "disable_csp", False)
            mode_settings.set("website", "log_filenames", log_filenames)
    else:
        # See what the persistent mode was
        mode = mode_settings.get("persistent", "mode")

    # In share and website mode, you must supply a list of filenames
    if mode == "share" or mode == "website":
        # Unless you passed in a persistent filename, in which case get the filenames from
        # the mode settings
        if (
            persistent_filename
            and not mode_settings.just_created
            and len(filenames) != 0
        ):
            filenames = mode_settings.get(mode, "filenames")

        else:
            # Make sure filenames given if not using receiver mode
            if len(filenames) == 0:
                if persistent_filename:
                    mode_settings.delete()

                parser.print_help()
                sys.exit()

            # Validate filenames
            valid = True
            for filename in filenames:
                if not os.path.isfile(filename) and not os.path.isdir(filename):
                    print(f"{filename} is not a valid file.")
                    valid = False
                if not os.access(filename, os.R_OK):
                    print(f"{filename} is not a readable file.")
                    valid = False
            if not valid:
                sys.exit()

        # Save the filenames in persistent file
        if persistent_filename:
            mode_settings.set(mode, "filenames", filenames)

    # In receive mode, you must allows either text, files, or both
    if mode == "receive" and disable_text and disable_files:
        print("You cannot disable both text and files")
        sys.exit()

    # Create the Web object
    web = Web(common, False, mode_settings, mode)

    # Start the Onion object
    try:
        onion = Onion(common, use_tmp_dir=True)
    except CannotFindTor:
        print("You must install tor to use OnionShare from the command line")
        if common.platform == "Darwin":
            print("In macOS, you can do this with Homebrew (https://brew.sh):")
            print("  brew install tor")
        sys.exit()

    try:
        onion.connect(
            custom_settings=False,
            config=config_filename,
            connect_timeout=connect_timeout,
            local_only=local_only,
        )
    except KeyboardInterrupt:
        print("")
        sys.exit()
    except Exception:
        sys.exit()

    # Start the onionshare app
    try:
        common.settings.load()

        # Receive mode needs to know the tor proxy details for webhooks
        if mode == "receive":
            if local_only:
                web.proxies = None
            else:
                (socks_address, socks_port) = onion.get_tor_socks_port()
                web.proxies = {
                    "http": f"socks5h://{socks_address}:{socks_port}",
                    "https": f"socks5h://{socks_address}:{socks_port}",
                }

        app = OnionShare(common, onion, local_only, autostop_timer)
        app.choose_port()

        # Delay the startup if a startup timer was set
        if autostart_timer > 0:
            # Can't set a schedule that is later than the auto-stop timer
            if autostop_timer > 0 and autostop_timer < autostart_timer:
                print(
                    "The auto-stop time can't be the same or earlier than the auto-start time. Please update it to start sharing."
                )
                sys.exit()

            app.start_onion_service(mode, mode_settings, False)
            url = f"http://{app.onion_host}"
            schedule = datetime.now() + timedelta(seconds=autostart_timer)
            if mode == "receive":
                print(
                    f"Files sent to you appear in this folder: {mode_settings.get('receive', 'data_dir')}"
                )
                print("")
                print(
                    "Warning: Receive mode lets people upload files to your computer. Some files can potentially take "
                    "control of your computer if you open them. Only open things from people you trust, or if you know "
                    "what you are doing."
                )
                print("")
                if not mode_settings.get("general", "public"):
                    print(
                        f"Give this address and private key to your sender, and tell them it won't be accessible until: {schedule.strftime('%I:%M:%S%p, %b %d, %y')}"
                    )
                    print(f"Private key: {app.auth_string}")
                else:
                    print(
                        f"Give this address to your sender, and tell them it won't be accessible until: {schedule.strftime('%I:%M:%S%p, %b %d, %y')}"
                    )
            else:
                if not mode_settings.get("general", "public"):
                    print(
                        f"Give this address and private key to your recipient, and tell them it won't be accessible until: {schedule.strftime('%I:%M:%S%p, %b %d, %y')}"
                    )
                    print(f"Private key: {app.auth_string}")
                else:
                    print(
                        f"Give this address to your recipient, and tell them it won't be accessible until: {schedule.strftime('%I:%M:%S%p, %b %d, %y')}"
                    )
            print(url)
            if mode_settings.get("general", "qr"):
                qr = QRCode()
                qr.add_data(url)
                print("Onion address as QR code:")
                qr.print_ascii()
                if not mode_settings.get("general", "public"):
                    qr.clear()
                    qr.add_data(app.auth_string)
                    print("Private key as QR code:")
                    qr.print_ascii()
            print("")
            print("Waiting for the scheduled time before starting...")
            app.onion.cleanup(False)
            time.sleep(autostart_timer)
            app.start_onion_service(mode, mode_settings)
        else:
            app.start_onion_service(mode, mode_settings)
    except KeyboardInterrupt:
        print("")
        sys.exit()
    except (TorTooOldEphemeral, TorTooOldStealth, TorErrorProtocolError) as e:
        print("")
        sys.exit()

    if mode == "website":
        # Prepare files to share
        try:
            web.website_mode.set_file_info(filenames)
        except OSError as e:
            print(e.strerror)
            sys.exit(1)

    if mode == "share":
        # Prepare files to share
        print("Compressing files.")
        try:
            web.share_mode.set_file_info(filenames)
        except OSError as e:
            print(e.strerror)
            sys.exit(1)

        # Warn about sending large files over Tor
        if web.share_mode.download_filesize >= 157_286_400:  # 150mb
            print("")
            print("Warning: Sending a large share could take hours")
            print("")

    # Start OnionShare http service in new thread
    t = threading.Thread(target=web.start, args=(app.port,))
    t.daemon = True
    t.start()

    try:  # Trap Ctrl-C
        time.sleep(0.2)

        # start auto-stop timer thread
        if app.autostop_timer > 0:
            app.autostop_timer_thread.start()

        # Build the URL
        url = f"http://{app.onion_host}"

        print("")
        if autostart_timer > 0:
            print("Server started")
        else:
            if mode == "receive":
                print(
                    f"Files sent to you appear in this folder: {mode_settings.get('receive', 'data_dir')}"
                )
                print("")
                print(
                    "Warning: Receive mode lets people upload files to your computer. Some files can potentially take "
                    "control of your computer if you open them. Only open things from people you trust, or if you know "
                    "what you are doing."
                )
                print("")

                if mode_settings.get("general", "public"):
                    print("Give this address to the sender:")
                    print(url)
                else:
                    print("Give this address and private key to the sender:")
                    print(url)
                    print(f"Private key: {app.auth_string}")
            else:
                if mode_settings.get("general", "public"):
                    print("Give this address to the recipient:")
                    print(url)
                else:
                    print("Give this address and private key to the recipient:")
                    print(url)
                    print(f"Private key: {app.auth_string}")
            if mode_settings.get("general", "qr"):
                qr = QRCode()
                qr.add_data(url)
                print("Onion address as QR code:")
                qr.print_ascii()
                if not mode_settings.get("general", "public"):
                    qr.clear()
                    qr.add_data(app.auth_string)
                    print("Private key as QR code:")
                    qr.print_ascii()

        print("")
        print("Press Ctrl+C to stop the server")

        # Wait for app to close
        while t.is_alive():
            if app.autostop_timer > 0:
                # if the auto-stop timer was set and has run out, stop the server
                if not app.autostop_timer_thread.is_alive():
                    if mode == "share":
                        # If there were no attempts to download the share, or all downloads are done, we can stop
                        if not web.share_mode.download_in_progress or web.share_mode.cur_history_id == 0 or web.done:
                            print("Stopped because auto-stop timer ran out")
                            web.stop(app.port)
                            break
                    elif mode == "receive":
                        if (
                            web.receive_mode.cur_history_id == 0
                            or not web.receive_mode.uploads_in_progress
                        ):
                            print("Stopped because auto-stop timer ran out")
                            web.stop(app.port)
                            break
                        web.receive_mode.can_upload = False
                    else:
                        # website or chat mode
                        print("Stopped because auto-stop timer ran out")
                        web.stop(app.port)
                        break
            # Allow KeyboardInterrupt exception to be handled with threads
            # https://stackoverflow.com/questions/3788208/python-threading-ignores-keyboardinterrupt-exception
            time.sleep(0.2)
    except KeyboardInterrupt:
        web.stop(app.port)
    finally:
        # Shutdown
        web.cleanup()
        t.join()
        onion.cleanup()


if __name__ == "__main__":
    main()
