import unittest

from core.engine import VisaScpiEngine


class FakeVisaResource:
    def __init__(self):
        self.commands = []
        self.closed = False
        self.timeout = None

    def clear(self):
        self.commands.append(("clear", None))

    def query(self, command):
        self.commands.append(("query", command))
        if command == "*IDN?":
            return "FakeScope,Model 1000,SN001,1.0"
        if command == ":WAV:PRE?":
            return "0,0,4,1,0.001,-0.001,0,0.02,-1.0,128"
        if command == ":TRIG:STAT?":
            return "READY"
        if command == ":MEAS:VPP? CHAN1":
            return "3.14"
        if command == ":MEAS:FREQ? CHAN1":
            return "1000"
        return "0"

    def write(self, command):
        self.commands.append(("write", command))

    def query_binary_values(self, command, datatype="B", container=list):
        self.commands.append(("query_binary_values", command, datatype))
        if command == ":WAV:DATA?":
            return container([128, 129, 130, 131])
        if command == ":DISP:DATA? PNG":
            return container([137, 80, 78, 71])
        raise AssertionError(command)

    def close(self):
        self.closed = True


class FakeResourceManager:
    def __init__(self):
        self.resource = FakeVisaResource()

    def list_resources(self):
        return ("USB0::FAKE::INSTR", "TCPIP0::192.168.1.10::INSTR")

    def open_resource(self, resource_name):
        self.opened = resource_name
        return self.resource


class VisaScpiEngineTests(unittest.TestCase):
    def test_discover_returns_visa_resources(self):
        engine = VisaScpiEngine(resource_manager=FakeResourceManager())

        resources = engine.discover()

        self.assertEqual(resources, ["USB0::FAKE::INSTR", "TCPIP0::192.168.1.10::INSTR"])

    def test_connect_opens_resource_and_queries_identity(self):
        manager = FakeResourceManager()
        engine = VisaScpiEngine(resource_manager=manager)

        idn = engine.connect("USB0::FAKE::INSTR")

        self.assertEqual(idn, "FakeScope,Model 1000,SN001,1.0")
        self.assertTrue(engine.connected)
        self.assertEqual(manager.opened, "USB0::FAKE::INSTR")
        self.assertIn(("query", "*IDN?"), manager.resource.commands)

    def test_generate_waveform_converts_binary_data_with_preamble(self):
        engine = VisaScpiEngine(resource_manager=FakeResourceManager())
        engine.connect("USB0::FAKE::INSTR")

        times, volts = engine.generate_waveform(1)

        self.assertEqual(times, [-0.001, 0.0, 0.001, 0.002])
        self.assertEqual(volts, [-1.0, -0.98, -0.96, -0.94])

    def test_exec_command_uses_query_for_question_commands_and_write_otherwise(self):
        manager = FakeResourceManager()
        engine = VisaScpiEngine(resource_manager=manager)
        engine.connect("USB0::FAKE::INSTR")

        result = engine.exec_command(":TRIG:STAT?")
        write_result = engine.exec_command(":RUN")

        self.assertEqual(result, "READY")
        self.assertEqual(write_result, "OK")
        self.assertIn(("write", ":RUN"), manager.resource.commands)


if __name__ == "__main__":
    unittest.main()
