from qns.entity.cchannel.cchannel import ClassicChannel, RecvClassicPacket, ClassicPacket
from qns.entity.node.app import Application
from qns.entity.qchannel.qchannel import QuantumChannel, RecvQubitPacket
from qns.entity.node.node import QNode
from qns.models.qubit.const import BASIS_X, BASIS_Z, \
    QUBIT_STATE_0, QUBIT_STATE_1, QUBIT_STATE_P, QUBIT_STATE_N
from qns.simulator.event import Event, func_to_event
from qns.simulator.simulator import Simulator
from qns.models.qubit import Qubit
from routing import SendPacketApp
#   from qns.simulator.ts import Time

import numpy as np

from qns.utils.rnd import get_rand, get_choice
# 加了密钥池容量的概念

capacity = 20000
min_requirement = 200


class QubitWithError(Qubit):
    def transfer_error_model(self, length: float, decoherence_rate: float = 0, **kwargs):
        lkm = length / 1000
        standand_lkm = 50.0
        theta = get_rand() * lkm / standand_lkm * np.pi / 4
        operation = np.array([[np.cos(theta), - np.sin(theta)], [np.sin(theta), np.cos(theta)]], dtype=np.complex128)
        self.state.operate(operator=operation)


class BB84SendApp(Application):
    def __init__(self, dest: QNode, qchannel: QuantumChannel,
                 cchannel: ClassicChannel, send_rate=1000):
        super().__init__()
        self.dest = dest
        self.qchannel = qchannel
        self.cchannel = cchannel
        self.send_rate = send_rate
        self.count = 0
        self.qubit_list = {}
        self.basis_list = {}
        self.measure_list = {}
        # self.time_flag = 0   # 初始化时间标记
        # self.change_time_flag = False
        # self.time_flag_queue = []
        self.waiting_length_queue = []
        self.waiting_msg_queue = []
        self.min_key = min_requirement
        # self.change_cur_pool = False

        self.pool_capacity = capacity  # 密钥池容量
        self.current_pool = 0   # 当前密钥池存储量
        self.temp_pool = 0
        self.succ_key_pool = {}
        self.fail_number = 0

        #   self.add_handler(self.handleClassicPacket, [RecvClassicPacket], [self.cchannel])

    def install(self, node: QNode, simulator: Simulator):
        super().install(node, simulator)

        time_list = []
        time_list.append(simulator.ts)

        t = simulator.ts
        event = func_to_event(t, self.succ_increase)
        self._simulator.add_event(event)
        # while t <= simulator.te:
        #     time_list.append(t)
        #     t = t + simulator.time(sec = 1 / self.send_rate)

        #     event = func_to_event(t, self.send_qubit)
        #     self._simulator.add_event(event)

    # def handleClassicPacket(self, node: QNode, event: Event):
    #     return self.check_basis(event)

    # def check_basis(self, event: RecvClassicPacket):
    #     packet = event.packet
    #     msg: dict = packet.get()
    #     id = msg.get("id")
    #     if id is None:      # request packet
    #         return False
    #     basis_dest = msg.get("basis")

    #     ret_dest = msg.get("ret")
    #     ret_src = self.measure_list[id]

    #     # qubit = self.qubit_list[id]
    #     basis_src = "Z" if (self.basis_list[id] == BASIS_Z).all() else "X"
    #     if basis_dest == basis_src and ret_dest == ret_src:
    #         # log.info(f"[{self._simulator.current_time}] src check {id} basis succ")
    #         self.succ_key_pool[id] = self.measure_list[id]
    #         # s: Simulator = self._simulator
    #         # t = s.tc
    #         if self.current_pool < self.pool_capacity:  # 向密钥池填充
    #             #   t.time_slot >= self.time_flag and self.current_pool < self.pool_capacity:
    #             self.current_pool += 1
    #             if len(self.waiting_length_queue) > 0 and self.change_cur_pool is False:
    #                 if self.current_pool-self.min_key > self.waiting_length_queue[0]:
    #                     self.change_cur_pool = True
    #                     self.waiting_length_queue.pop(0)
    #                     sendapp = self._node.get_apps(SendPacketApp).pop(0)
    #                     mssg = self.waiting_msg_queue.pop(0)
    #                     event = func_to_event(self._simulator.tc, sendapp.send_app_packet, info=mssg, qchannel=self.qchannel)
    #                     self._simulator.add_event(event)
    #     else:
    #         # log.info(f"[{self._simulator.current_time}] src check {id} basis fail")
    #         self.fail_number += 1

    #     packet = ClassicPacket(msg={"id": id, "basis": basis_src,
    #                            "ret": self.measure_list[id]}, src=self._node, dest=self.dest)
    #     self.cchannel.send(packet, next_hop=self.dest)
    #     return True

    # def send_qubit(self):

    #     # randomly generate a qubit
    #     state = get_choice([QUBIT_STATE_0, QUBIT_STATE_1,
    #                         QUBIT_STATE_P, QUBIT_STATE_N])
    #     qubit = Qubit(state=state)
    #     basis = BASIS_Z if (state == QUBIT_STATE_0).all() or (
    #         state == QUBIT_STATE_1).all() else BASIS_X
    #     # basis_msg = "Z" if (basis == BASIS_Z).all() else "X"

    #     ret = 0 if (state == QUBIT_STATE_0).all() or (
    #         state == QUBIT_STATE_P).all() else 1

    #     qubit.id = self.count
    #     self.count += 1
    #     self.qubit_list[qubit.id] = qubit
    #     self.basis_list[qubit.id] = basis
    #     self.measure_list[qubit.id] = ret

    #     # log.info(f"[{self._simulator.current_time}] send qubit {qubit.id},\
    #     #  basis: {basis_msg} , ret: {ret}")
    #     self.qchannel.send(qubit=qubit, next_hop=self.dest)

    #     t = self._simulator.current_time + \
    #         self._simulator.time(sec=1 / self.send_rate)
    #     event = func_to_event(t, self.send_qubit, by=self)
    #     self._simulator.add_event(event)

    def succ_increase(self):
        if self.current_pool < self.pool_capacity:  # and self.change_cur_pool is False
            # self.change_cur_pool = True
            self.current_pool += 1
            # self.current_pool += self.temp_pool
            # self.temp_pool = 0
            # recvbb84s = self.dest.get_apps(BB84RecvApp)
            # for recvbb84 in recvbb84s:
            #     if recvbb84.qchannel == self.qchannel:
            #         recv = recvbb84
            #         break
            # recv.current_pool += recv.temp_pool
            # recv.temp_pool = 0
            # self.change_cur_pool = False
        # else:
        #     self.temp_pool += 1
        if len(self.waiting_length_queue) > 0:# and self.change_cur_pool is False
            if self.current_pool-self.min_key > self.waiting_length_queue[0]:
                # self.change_cur_pool = True
                self.waiting_length_queue.pop(0)
                sendapp = self._node.get_apps(SendPacketApp).pop(0)
                mssg = self.waiting_msg_queue.pop(0)
                event = func_to_event(self._simulator.tc, sendapp.send_app_packet, by=self._node, info=mssg, qchannel=self.qchannel)
                self._simulator.add_event(event)
        t = self._simulator.current_time + self._simulator.time(sec=1/self.send_rate)
        event = func_to_event(t, self.succ_increase, by=self)
        self._simulator.add_event(event)


class BB84RecvApp(Application):
    def __init__(self, src: QNode, qchannel: QuantumChannel, cchannel: ClassicChannel, send_rate=1000):
        super().__init__()
        self.src = src
        self.qchannel = qchannel
        self.cchannel = cchannel

        self.qubit_list = {}
        self.basis_list = {}
        self.measure_list = {}
        self.pool_capacity = capacity  # 密钥池容量
        self.current_pool = 0   # 当前密钥池存储量
        self.temp_pool = 0
        self.waiting_length_queue = []
        self.waiting_msg_queue = []
        self.send_rate = send_rate
        self.min_key = min_requirement

        self.succ_key_pool = {}
        self.fail_number = 0
        #   self.add_handler(self.handleQuantumPacket, [RecvQubitPacket], [self.qchannel])
        #   self.add_handler(self.handleClassicPacket, [RecvClassicPacket], [self.cchannel])

    def install(self, node: QNode, simulator: Simulator):
        super().install(node, simulator)
        t = simulator.ts
        event = func_to_event(t, self.succ_increase)
        self._simulator.add_event(event)

    # def handleQuantumPacket(self, node: QNode, event: Event):
    #     return self.recv(event)

    # def handleClassicPacket(self, node: QNode, event: Event):
    #     return self.check_basis(event)

    # def check_basis(self, event: RecvClassicPacket):
    #     packet = event.packet
    #     msg: dict = packet.get()
    #     id = msg.get("id")
    #     if id is None:  # request packet
    #         return False
    #     basis_src = msg.get("basis")

    #     # qubit = self.qubit_list[id]
    #     basis_dest = "Z" if (self.basis_list[id] == BASIS_Z).all() else "X"

    #     ret_dest = self.measure_list[id]
    #     ret_src = msg.get("ret")

    #     if basis_dest == basis_src and ret_dest == ret_src:
    #         # log.info(f"[{self._simulator.current_time}] dest check {id} basis succ")
    #         self.succ_key_pool[id] = self.measure_list[id]
    #         #   flag = msg.get("flag")
    #         if self.current_pool < self.pool_capacity:  # 向密钥池填充
    #             self.current_pool += 1
    #             if len(self.waiting_length_queue) > 0:
    #                 if self.current_pool-self.min_key >= self.waiting_length_queue[0]:
    #                     sendbb84s = self.src.get_apps(BB84SendApp)
    #                     for sendbb84 in sendbb84s:
    #                         if sendbb84.qchannel == self.qchannel:
    #                             break
    #                     if sendbb84.change_cur_pool is False:
    #                         sendbb84.change_cur_pool = True
    #                         self.waiting_length_queue.pop(0)
    #                         sendapp = self._node.get_apps(SendPacketApp).pop(0)
    #                         mssg = self.waiting_msg_queue.pop(0)
    #                         event = func_to_event(self._simulator.tc, sendapp.send_app_packet, info=mssg, qchannel=self.qchannel)
    #                         self._simulator.add_event(event)
    #     else:
    #         # log.info(f"[{self._simulator.current_time}] dest check {id} basis fail")
    #         self.fail_number += 1
    #     return True

    # def recv(self, event: RecvQubitPacket):
    #     qubit: Qubit = event.qubit
    #     # randomly choose X,Z basis
    #     basis = get_choice([BASIS_Z, BASIS_X])
    #     basis_msg = "Z" if (basis == BASIS_Z).all() else "X"
    #     ret = qubit.measureZ() if (basis == BASIS_Z).all() else qubit.measureX()
    #     self.qubit_list[qubit.id] = qubit
    #     self.basis_list[qubit.id] = basis
    #     self.measure_list[qubit.id] = ret

    #     # log.info(f"[{self._simulator.current_time}] recv qubit {qubit.id}, \
    #     # basis: {basis_msg}, ret: {ret}")
    #     packet = ClassicPacket(
    #         msg={"id": qubit.id, "basis": basis_msg, "ret": ret}, src=self._node, dest=self.src)
    #     self.cchannel.send(packet, next_hop=self.src)

    def succ_increase(self):
        # print("increase cur key", self._node, self._simulator.tc)
        if self.current_pool < self.pool_capacity:
            # sendbb84s = self.src.get_apps(BB84SendApp)
            # for sendbb84 in sendbb84s:
            #     if sendbb84.qchannel == self.qchannel:
            #         send = sendbb84
            #         break
            # if send.change_cur_pool is False:
            #     send.change_cur_pool = True
            self.current_pool += 1
            #     self.current_pool += self.temp_pool
            #     self.temp_pool = 0
            #     send.current_pool += send.temp_pool
            #     send.temp_pool = 0
            #     send.change_cur_pool = False
            # else:
            #     self.temp_pool += 1
        if len(self.waiting_length_queue) > 0:
            if self.current_pool-self.min_key > self.waiting_length_queue[0]:
                # sendbb84s = self.src.get_apps(BB84SendApp)
                # for send in sendbb84s:
                #     if send.qchannel == self.qchannel:
                #         sendbb84 = send
                #         break
                # if sendbb84.change_cur_pool is False:
                #     sendbb84.change_cur_pool = True
                self.waiting_length_queue.pop(0)
                sendapp = self._node.get_apps(SendPacketApp).pop(0)
                mssg = self.waiting_msg_queue.pop(0)
                event = func_to_event(self._simulator.tc, sendapp.send_app_packet, by=self._node, info=mssg, qchannel=self.qchannel)
                self._simulator.add_event(event)
        t = self._simulator.current_time + self._simulator.time(sec=1/self.send_rate)
        event = func_to_event(t, self.succ_increase)
        self._simulator.add_event(event)
