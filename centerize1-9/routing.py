from qns.entity.node.app import Application
from qns.entity.node.node import QNode
from qns.entity.cchannel.cchannel import ClassicChannel, ClassicPacket, RecvClassicPacket
from qns.entity.qchannel.qchannel import QuantumChannel
from qns.simulator.event import func_to_event, Event
from qns.simulator.simulator import Simulator
from qns.network.requests import Request
from qns.network.network import QuantumNetwork

packet_length = 500


def search_app(sapps, rapps, qchannel_name: str = ""):   # 得到qchannel对应的bb84app
    temps = None
    tempr = None
    for app in sapps:
        if app.qchannel.name == qchannel_name:
            temps = app
            break
    for app in rapps:
        if app.qchannel.name == qchannel_name:
            tempr = app
            break
    return temps, tempr


def start_time_order(re_list: list[Request], s: int, e: int):
    if s >= e:
        return
    val = re_list[e].attr["start time"]
    left = s
    right = e
    while left < right:
        while re_list[left].attr["start time"] < val and left < right:
            left += 1
        while re_list[right].attr["start time"] >= val and left < right:
            right -= 1
        if left < right:
            temp = re_list[left]
            re_list[left] = re_list[right]
            re_list[right] = temp
    if re_list[left].attr["start time"] < val:
        left += 1
    temp = re_list[left]
    re_list[left] = re_list[e]
    re_list[e] = temp
    start_time_order(re_list, s, left-1)
    start_time_order(re_list, left+1, e)


class SendPacketApp(Application):
    def __init__(self, node: QNode, net: QuantumNetwork, bb84rapps: list, bb84sapps: list, reject_app_packet_symbol: dict, request_list: list[Request] = [], request_management: dict = {}):
        super().__init__()
        self.request_list = request_list
        self.bb84sapps = bb84sapps
        self.bb84rapps = bb84rapps
        self.count = 0
        self.request_management = request_management
        self.reject_app__packet_symbol = reject_app_packet_symbol
        self.net = net
        self.reject_app_packet_symbol = {}
        self.consume_key = 0

    def install(self, node: QNode, simulator: Simulator):
        super().install(node, simulator)
        # self.request_list.sort(Request.attr["start time"])
        self._simulator = simulator
        self._node = node
        if len(self.request_list) > 0:
            re = self.request_list.pop(0)
            temp = re.attr["start time"]
            t = temp + simulator.ts
            # print(re.attr, t)
            event = func_to_event(t, self.send_packet, by=self, re=re)
            self._simulator.add_event(event)

    def send_packet(self, re: Request):     # 不能一起发，延时超过只会浪费一个包的密钥量
        if len(self.request_list) > 0:
            r = self.request_list.pop(0)
            temp = r.attr["start time"]
            t = temp + self._simulator.ts
            # print(re.attr, t)
            event = func_to_event(t, self.send_packet, by=self, re=r)
            self._simulator.add_event(event)
        src = re.src
        dest = re.dest
        attr = re.attr
        route_result = self.net.query_route(src, dest)
        path = route_result[0]
        next_hop = path[1]
        symbol = f"{self.get_node().name}-{self.count}"
        self.count += 1
        self.request_management[symbol] = re
        key_requirement = attr.get("key requirement")
        tc_slot = self._simulator.tc.time_slot
        print("start routing: ", re, attr)
        #   info: dict = {}
        #   info["symbol"] = symbol
        #   info["src"] = src
        #   info["dest"] = dest
        #   info["delay"] = self.request_management[symbol]["attr"].get("delay")
        delay = attr.get("delay")
        #   sendapp = self._node.get_apps(SendRoutingApp).pop(0)
        qchannel: QuantumChannel = self._node.get_qchannel(next_hop)
        sendbb84, recvbb84 = search_app(self.bb84sapps, self.bb84rapps, qchannel.name)
        if sendbb84.get_node() == self._node:     # 保证在自己的节点上面排队
            app = sendbb84
        elif recvbb84.get_node() == self._node:
            app = recvbb84
        while key_requirement > 0:  # 发送数据包
            if key_requirement >= packet_length:
                mssg = {"symbol": symbol, "length": packet_length, "dest": dest.name, "key requirement": attr.get("key requirement"),
                        "start routing time": tc_slot, "delay": delay}
                #   event = func_to_event(self._simulator.tc, sendapp.send_app_packet, info=info, order=order, data_packet_length=packet_length, first_node=True)   # , None, None
                key_requirement -= packet_length
                app.waiting_length_queue.append(packet_length)
            else:
                app.waiting_length_queue.append(key_requirement)
                mssg = {"symbol": symbol, "length": key_requirement, "dest": dest.name, "key requirement": attr.get("key requirement"),
                        "start routing time": tc_slot, "delay": delay}
                #   event = func_to_event(self._simulator.tc, sendapp.send_app_packet, info=info, order=order, data_packet_length=key_requirement, first_node=True)
                key_requirement = 0
            #   self._simulator.add_event(event)
            app.waiting_msg_queue.append(mssg)

    def send_app_packet(self, info: dict, qchannel: QuantumChannel):
        #   , order: int, data_packet_length: int = 0, first_node: bool = True
        #   length stands for single key requirement
        sym = info["symbol"]
        if self.reject_app_packet_symbol.get(sym) is True:
            return
        dest = self.net.get_node(info["dest"])
        route_result = self.net.query_route(self._node, dest)
        path = route_result[0]
        next_hop = path[1]
        #   qchannel: QuantumChannel = self._node.get_qchannel(next_hop)
        sendbb84, recvbb84 = search_app(self.bb84sapps, self.bb84rapps, qchannel.name)
        # 两者之间最多差一个bit，存在min key，不会有只有一个达到密钥量的情况、send大于，recv不小于
        if info["delay"] + info["start routing time"] > self._simulator.tc.time_slot:
            sendbb84.current_pool -= info["length"]
            recvbb84.current_pool -= info["length"]
            self.consume_key += info["length"]
            msg = info
            cchannel: ClassicChannel = self._node.get_cchannel(next_hop)
            packet = ClassicPacket(msg=msg, src=self._node, dest=next_hop)
            cchannel.send(packet=packet, next_hop=next_hop)
            # print("routing:", info)
        else:   # 超过延时，路由失败
            #   if self.reject_app_packet_symbol[sym] is None:
            self.reject_app_packet_symbol[sym] = True
            # msg = {"symbol": sym, "type": "routing answer", "answer": "no", "order": info["order"]}
            # next_hop = self.request_management[sym]["src"]
            # cchannel: ClassicChannel = self._node.get_cchannel(next_hop)
            # packet = ClassicPacket(msg=msg, src=self._node, dest=next_hop)
            # cchannel.send(packet=packet, next_hop=next_hop)
        # sendbb84.change_cur_pool = False


class RecvPacketApp(Application):
    def __init__(self, net: QuantumNetwork, node: QNode, reject_app_packet_symbol: dict, bb84_sapps: list, bb84_rapps: list, succ_request: list = []):
        super().__init__()
        self.bb84sapps = bb84_sapps
        self.bb84rapps = bb84_rapps
        self.net = net
        self.reject_app_packet_symbol = reject_app_packet_symbol
        self.recv_management = {}
        self.success_request = succ_request

    def install(self, node, simulator: Simulator):
        super().install(node, simulator)
        self._simulator = simulator
        self._node = node
        self.add_handler(self.handleClassicPacket, [RecvClassicPacket], [])

    def handleClassicPacket(self, node: QNode, event: Event):
        if isinstance(event, RecvClassicPacket):
            packet = event.packet
            # get the packet message
            msg = packet.get()
            #   coming_cchannel = event.cchannel
            symbol = msg["symbol"]
            dest = self.net.get_node(msg["dest"])
            if dest == self._node:
                if self.recv_management.get(symbol) is None:
                    self.recv_management[symbol] = msg["length"]
                else:
                    self.recv_management[symbol] += msg["length"]
                    if self.recv_management[symbol] == msg["key requirement"]:
                        self.success_request.append(symbol)
            else:
                if self.reject_app_packet_symbol.get(symbol) is None:
                    #   前序包均已在此链路上路由成功，没有超过延时
                    length = msg["length"]
                    route_result = self.net.query_route(self._node, dest)
                    path = route_result[0]
                    next_hop = path[1]
                    qchannel: QuantumChannel = self._node.get_qchannel(next_hop)
                    sendbb84, recvbb84 = search_app(self.bb84sapps, self.bb84rapps, qchannel.name)
                    if sendbb84.get_node() == self._node:
                        app = sendbb84
                    elif recvbb84.get_node() == self._node:
                        app = recvbb84
                    app.waiting_length_queue.append(length)
                    app.waiting_msg_queue.append(msg)
