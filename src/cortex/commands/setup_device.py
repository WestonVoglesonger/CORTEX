"""Setup-device command — one-time provisioning for remote benchmarking."""


def setup_parser(parser):
    """Setup argument parser for setup-device command."""
    parser.add_argument(
        "device",
        help="Device string (user@host)"
    )
    parser.add_argument(
        "--ssh-port", "-p",
        type=int,
        default=22,
        help="SSH port (default: 22)"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Check provisioning status without modifying device"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output"
    )


def execute(args):
    """Execute setup-device command."""
    from cortex.deploy.provisioner import DeviceProvisioner

    # Parse user@host
    if "@" not in args.device:
        print(f"Error: device must be user@host, got '{args.device}'")
        return 1

    user, host = args.device.split("@", 1)

    provisioner = DeviceProvisioner(user, host, ssh_port=args.ssh_port)

    if args.verify:
        print(f"Checking provisioning status for {args.device}...")
        if provisioner.verify():
            print(f"  ✓ {args.device} is provisioned for CORTEX")
            return 0
        else:
            print(f"  ✗ {args.device} is NOT provisioned")
            print(f"  Run: cortex setup-device {args.device}")
            return 1

    print(f"Provisioning {args.device} for CORTEX benchmarking...")
    print(f"  This installs sudoers rules, logind config, and sysctl settings.")
    print()

    if provisioner.provision(verbose=args.verbose):
        print()
        print(f"✓ {args.device} provisioned successfully")
        print(f"  You can now run: cortex run --device {args.device}")
        return 0
    else:
        print()
        print(f"✗ Provisioning failed for {args.device}")
        print(f"  Re-run with --verbose for details")
        return 1
