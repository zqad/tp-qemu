import logging
import time
from autotest.client.shared import error
from virttest import utils_misc

try:
    from virttest.staging import utils_memory
except ImportError:
    from autotest.client.shared import utils_memory

from virttest import env_process


@error.context_aware
def run(test, params, env):
    """
    KVM reboot time test:
    1) Set init run level to 1
    2) Restart guest
    3) Wait for the console
    4) Send a 'reboot' command to the guest
    5) Boot up the guest and measure the boot time
    6) Restore guest run level

    :param test: QEMU test object
    :param params: Dictionary with the test parameters
    :param env: Dictionary with test environment
    """

    vm = env.get_vm(params["main_vm"])
    vm.verify_alive()
    timeout = int(params.get("login_timeout", 360))
    session = vm.wait_for_login(timeout=timeout)
    vm_params = params

    error.context("Set guest run level to 1", logging.info)
    if params.get("kernel", False):
        # If the configuration has a kernel argument, we are using qemu as a
        # bootloader and can just modify the kernel_params variable
        vm_params = params.copy()
        vm_params.update({'kernel_params':
                          "%s S" % params.get("kernel_params")})
    else:
        single_user_cmd = params['single_user_cmd']
        session.cmd(single_user_cmd)

    try:
        error.context("Restart guest", logging.info)
        session.cmd('sync')
        vm.destroy()

        error.context("Boot up guest", logging.info)
        vm.create(params=vm_params)
        vm.verify_alive()
        session = vm.wait_for_serial_login(timeout=timeout)

        error.context("Send a 'reboot' command to the guest", logging.info)
        utils_memory.drop_caches()
        session.cmd('/sbin/reboot; sleep 3600', timeout=1,
                    ignore_all_errors=True)
        before_reboot_stamp = utils_misc.monotonic_time()

        error.context("Boot up the guest and measure the boot time",
                      logging.info)
        session = vm.wait_for_serial_login(timeout=timeout)
        reboot_time = utils_misc.monotonic_time() - before_reboot_stamp
        test.write_test_keyval({'result': "%ss" % reboot_time})
        expect_time = int(params.get("expect_reboot_time", "30"))
        logging.info("Reboot time: %ss" % reboot_time)

    finally:
        try:
            error.context("Restore guest run level", logging.info)
            restore_level_cmd = params['restore_level_cmd']
            if not params.get("kernel", False):
                session.cmd(restore_level_cmd)
                session.cmd('sync')
            vm.destroy(gracefully=False)
            env_process.preprocess_vm(test, params, env, vm.name)
            vm.verify_alive()
            vm.wait_for_login(timeout=timeout)
        except Exception:
            logging.warning("Can not restore guest run level, "
                            "need restore the image")
            params["restore_image_after_testing"] = "yes"

    if reboot_time > expect_time:
        raise error.TestFail(
            "Guest reboot is taking too long: %ss" % reboot_time)

    session.close()
