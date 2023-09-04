from qns.entity.node.app import Application
from qns.network.requests import Request
from qns.entity.node.node import QNode
from qns.simulator.simulator import Simulator
from qns.simulator.event import func_to_event, Event
from qns.entity.cchannel.cchannel import ClassicChannel, ClassicPacket, RecvClassicPacket
from qns.entity.qchannel.qchannel import QuantumChannel
#   from threshold_bb84 import BB84RecvApp, BB84SendApp
from waxman_model import WaxmanTopology
from qns.network import QuantumNetwork
import numpy as np
import math
from create_request_ton import time_accuracy as accuracy

packet_length = 500
beta = 0.5
aerfa = 0.5
q_length = 1000  # 与drop_rate有关
c_length = 1000
light_speed = 299791458
time_waiting_resource = 0.1
#   second


def distance(node: QNode, dest: QNode, topo: WaxmanTopology):
    if node == dest:
        return 0
    node_name = node.name
    dest_name = dest.name
    if int(node_name[1:]) < int(dest_name[1:]):
        temp = topo.distance_table[(node, dest)]
    else:
        temp = topo.distance_table[(dest, node)]
    return temp


def send_calculate_link_value(net: QuantumNetwork, topo: WaxmanTopology, node: QNode, symbol: str, dest: QNode, rapps, restrict: dict, coming_node: QNode = None):
    # greedy mode need to use this function     , coming_ccnannel: ClassicChannel = None
    num = 0
    another_dist: dict = {}
    node_dest_distance = distance(node, dest, topo)
    #   if coming_ccnannel is not None:
    #       restrict = cchannel
    for qchannel in node.qchannels:     # 找到节点的所有邻居(向距离更近的node寻求信息)
        node_list = qchannel.node_list
        for i in node_list:
            if i == node:
                continue
            another = i
            break
        if another == coming_node:  # 实际上不会有来的node，距离要求不满足
            continue
        temp = distance(another, dest, topo)
        if temp < node_dest_distance:
            for rapp in rapps:
                if rapp.qchannel == qchannel:
                    break
            simulator: Simulator = rapp.get_simulator()
            if rapp.current_pool - rapp.min_key > 0:
                flag = False
                for item in restrict[another.name].items():
                    limit_time = item[1]["time"]
                    limit_dest = net.get_node(item[0])
                    limit_dist = item[1]["distance"]
                    dest_location = topo.location_table[dest]
                    limit_dest_location = topo.location_table[limit_dest]
                    dist_diff = np.sqrt((dest_location[0] - limit_dest_location[0]) ** 2 + (dest_location[1] - limit_dest_location[1]) ** 2)
                    if dist_diff <= limit_dist and simulator.tc.time_slot <= limit_time:
                        flag = True
                        break
                if flag is False:
                    # 可以走
                    another_dist[qchannel.name] = temp
                    num += 1
                    msg = {"type": "calculation", "symbol": symbol}
                    #  , "src": node.name, "dest": another.name
                    cchannel: ClassicChannel = node.get_cchannel(another)
                    packet = ClassicPacket(msg=msg, src=node, dest=another)
                    cchannel.send(packet=packet, next_hop=another)
            else:
                #   if another == dest:
                #    hop = 0
                #   else:
                #    route_list = net.query_route(src=another, dest=dest)
                #    route = route_list[0]
                #    hop = route[0]
                hop = 1
                t_cache = simulator.tc.time_slot + hop * ((c_length * 2 + q_length) / light_speed) * accuracy
                restrict[another.name][dest.name] = {"distance": temp/2, "time": t_cache}
                #   "dest": dest.name, "next_hop": another.name,
    return num, another_dist


def search_right_hand(net: QuantumNetwork, topo: WaxmanTopology, node: QNode, dest: QNode, rapps, restrict: dict, coming_node: QNode = None, temp_restrict: dict = None, symbol: str = None):
    neighbor_node: dict = {}
    node_location = topo.location_table[node]
    for qchannel in node.qchannels:     # 找到节点的所有邻居，除了coming node
        node_list = qchannel.node_list
        for i in node_list:
            if i == node:
                continue
            another = i
            break
        if coming_node is not None and another == coming_node:
            continue
        another_location = topo.location_table[another]
        x_diff = another_location[0] - node_location[0]
        y_diff = another_location[1] - node_location[1]
        neighbor_node[another] = (x_diff, y_diff)
    dest_location = topo.location_table[dest]
    x_dest_diff = dest_location[0] - node_location[0]
    y_dest_diff = dest_location[1] - node_location[1]
    dest_arc = math.atan2(y_dest_diff, x_dest_diff)
    neighbor_arc: dict = {}
    for i in neighbor_node.items():
        another = i[0]
        dist = i[1]
        temp = math.atan2(dist[1], dist[0])
        if temp < dest_arc:
            temp += np.pi * 2
        neighbor_arc[another] = temp
    neighbor_queue = sorted(neighbor_arc.items(), key=lambda s: s[1], reverse=False)
    aim = None
    for i in neighbor_queue:
        another = i[0]
        for rapp in rapps:
            if rapp.qchannel == qchannel:
                break
        simulator: Simulator = rapp.get_simulator()
        if rapp.current_pool - rapp.min_key > 0:
            flag = False
            for item in restrict[another.name].items():
                limit_time = item[1]["time"]
                limit_dest = net.get_node(item[0])
                limit_dist = item[1]["distance"]
                dest_location = topo.location_table[dest]
                limit_dest_location = topo.location_table[limit_dest]
                dist_diff = np.sqrt((dest_location[0] - limit_dest_location[0]) ** 2 + (dest_location[1] - limit_dest_location[1]) ** 2)
                if dist_diff <= limit_dist and simulator.tc.time_slot <= limit_time:
                    flag = True
                    break
            if temp_restrict is not None and temp_restrict.get(another.name) is True:
                flag = True
            if flag is False:
                # 可以走
                aim = another
                return aim
        else:
            #   if another == dest:
            #    hop = 0
            #   else:
            #    route_list = net.query_route(src=another, dest=dest)
            #    route = route_list[0]
            #    hop = route[0]
            hop = 1
            t_cache = simulator.tc.time_slot + hop * ((c_length * 2 + q_length) / light_speed) * accuracy
            restrict[another.name][dest.name] = {"distance": temp/2, "time": t_cache}
    return aim


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


def create_request_info(request_management: dict, sym: str, re: Request):
    request_management[sym] = {}
    request_management[sym]["dest"] = re.dest
    request_management[sym]["src"] = re.src
    request_management[sym]["attr"] = re.attr
    request_management[sym]["state"] = "finding"
    #   routing/successful/failed                      /rerouting/refinding
    request_management[sym]["request times"] = 1
    request_management[sym]["start routing"] = 0
    #   the time when first application packet is sent by src
    request_management[sym]["end routing"] = 0
    #   the time when last application packet is received by dest
    request_management[sym]["packet arrival"] = {}
    request_management[sym]["packet number"] = math.ceil(re.attr["key requirement"] / packet_length)
    #   for i in range(math.ceil(re.attr["key requirement"] / packet_length)):
    #       request_management[sym]["packet arrival"][i] = False


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


def search_next_hop(net: QuantumNetwork, node: QNode, dest: QNode, routing_table: dict, simulator: Simulator, info: dict, sapps, rapps):
    msg = info["msg"]
    mode = msg["mode"]
    symbol = msg["symbol"]
    if mode == "greedy":
        F_list: dict = {}
        Q_list: dict = {}
        P_list: dict = {}
        R_list: dict = {}
        T_last = (c_length * 2 + q_length) / light_speed + 1 / accuracy   # 固定？only public channnel    
        T_average = (c_length * 2 + q_length) / light_speed + 1 / accuracy
        val = info["value"]
        #   找Mthr
        for item in info["Mthr list"].items():
            if item[1] > val:
                key = item[0]
                info["Mthr list"][key] = val
            q_name = item[0]
            sendbb84, recvbb84 = search_app(sapps=sapps, rapps=rapps, qchannel_name=q_name)
            cur_key = min(sendbb84.current_pool, recvbb84.current_pool)
            max_key = sendbb84.pool_capacity
            Q_value = cur_key**2 * item[1] / max_key**3
            Q_list[q_name] = 1 - Q_value / math.exp(1 - Q_value)
            time_span = simulator.tc.time_slot - recvbb84.time_flag
            T_value = (T_last + time_span / simulator.accuracy) / (2 * T_average)
            P_list[q_name] = T_value
            R_list[q_name] = aerfa * Q_list[q_name] + (1 - aerfa) * P_list[q_name]
            G_value = info["another dist"][q_name]
            F_list[q_name] = (1 - beta) * R_list[q_name] + beta * G_value
        min_F_value = float('inf')
        key = None
        for item in F_list.items():
            if item[1] < min_F_value:
                min_F_value = item[1]
                key = item[0]
        for qchannel in node.qchannels:
            if qchannel.name == key:
                break
        node_list = qchannel.node_list
        if node_list[0] == node:
            another = node_list[1]
        else:
            another = node_list[0]
        routing_table[dest.name][symbol] = another  # 更新路由表
        cchannel: ClassicChannel = node.get_cchannel(another)
        packet = ClassicPacket(msg=msg, src=node, dest=another)
        cchannel.send(packet=packet, next_hop=another)


class SendRoutingApp(Application):
    def __init__(self, net: QuantumNetwork, node: QNode, topo: WaxmanTopology, send_mode: dict, restrict: dict, reject_app_packet_symbol: dict, link_value: dict, bb84_sapps,
                 bb84_rapps, request_management: dict = {}, routing_info: dict = {}):
        # 以请求为单位进行管理， 以目的节点为索引进行寻路
        super().__init__()
        self.bb84sapps = bb84_sapps
        self.bb84rapps = bb84_rapps
        self.request_list = node.requests
        self.request_management = request_management
        self.link_value = link_value
        self.routing_table = routing_info
        self.restrict = restrict
        self.send_mode = send_mode
        self.count = 0
        self.topo = topo
        self.net = net
        self.reject_app_packet_symbol = reject_app_packet_symbol
        self.consume_key = 0

    def install(self, node: QNode, simulator: Simulator):
        super().install(node, simulator)
        self._simulator = simulator
        self._node = node
        if len(self.request_list) > 0:
            re = self.request_list.pop(0)
            temp = re.attr["start time"]
            t = temp+simulator.ts
            # print(re.attr, t)
            event = func_to_event(t, self.send_re_packet, re=re, first_flag=True)
            self._simulator.add_event(event)

    def send_re_packet(self, re: Request, first_flag: bool, symbol: str = ""):    # 首发节点
        if len(self.request_list) > 0:
            r = self.request_list.pop(0)
            temp = r.attr["start time"]
            t = temp+self._simulator.ts
            # print(re.attr, t)
            event = func_to_event(t, self.send_re_packet, re=r, first_flag=True)
            self._simulator.add_event(event)
        #   src = re.src
        dest = re.dest
        attr = re.attr
        if first_flag:  # 第一次路由
            symbol = f"{self._node.name}-{self.count}"
            self.count += 1
            create_request_info(self.request_management, symbol, re)
        num, another_dist = send_calculate_link_value(net=self.net, topo=self.topo, node=self._node, symbol=symbol, dest=dest, rapps=self.bb84rapps, restrict=self.restrict)
        if num > 0:
            # greedy
            msg = {"symbol": symbol, "type": "finding", "mode": "greedy", "loop": 0, "RecPosition": None, "RecIF": None,
                   "key requirement": attr["key requirement"], "request times": self.request_management[symbol]["request times"]}
            #   , "request times": self.request_management[symbol]["request times"]
            #   一开始是贪婪模式，不存在恢复模式需要的信息
            self.link_value[symbol] = {}
            self.link_value[symbol]["Mthr list"] = {}
            self.link_value[symbol]["msg"] = msg
            self.link_value[symbol]["number"] = num
            self.link_value[symbol]["another dist"] = another_dist
            temp = 0    # 计算自己节点的L
            for qchannel in self._node.qchannels:
                sendbb84, recvbb84 = search_app(self.bb84sapps, self.bb84rapps, qchannel.name)
                s_curr = sendbb84.current_pool
                r_curr = recvbb84.current_pool
                curr = min(s_curr, r_curr)
                temp += curr
            val = temp / len(self._node.qchannels)
            self.link_value[symbol]["value"] = val
            self.send_mode[symbol] = "greedy"
            print("start finding: ", msg)
        else:   # recovery
            next_hop = search_right_hand(net=self.net, topo=self.topo, node=self._node, dest=dest, rapps=self.bb84rapps, restrict=self.restrict)
            if next_hop is None:    # "原路返回"， 在这里即重新寻路
                self.routing_table[dest.name][symbol] = None
                self.request_management[symbol]["request times"] += 1
                t = self._simulator.tc + self._simulator.time(sec=time_waiting_resource)
                event = func_to_event(t, self.send_re_packet, re=re, first_flag=False, symbol=symbol)
                self._simulator.add_event(event)
                self.send_mode[symbol] = "no"
                print("prepare to restart routing", re.src, re.dest, re.attr)
            else:
                self.routing_table[dest.name][symbol] = next_hop
                msg = {"symbol": symbol, "type": "finding", "mode": "recovery", "loop": 0, "RecPosition": self._node.name, "RecIF": None,
                       "key requirement": attr["key requirement"], "request times": self.request_management[symbol]["request times"]}
                cchannel: ClassicChannel = self._node.get_cchannel(next_hop)
                packet = ClassicPacket(msg=msg, src=self._node, dest=next_hop)
                cchannel.send(packet=packet, next_hop=next_hop)
                self.send_mode[symbol] = "recovery"
                print("start finding: ", msg)

    def send_app_packet(self, info: dict, qchannel: QuantumChannel):
        #   , order: int, data_packet_length: int = 0, first_node: bool = True
        #   length stands for single key requirement
        sym = info["symbol"]
        if self.reject_app_packet_symbol.get(sym) is True:
            return
        dest = self.request_management[sym]["dest"]
        next_hop = self.routing_table[dest.name][sym]
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
        else:   # 超过延时，路由失败
            #   if self.reject_app_packet_symbol[sym] is None:
            self.reject_app_packet_symbol[sym] = True
            msg = {"symbol": sym, "type": "routing answer", "answer": "no", "order": info["order"]}
            next_hop = self.request_management[sym]["src"]
            cchannel: ClassicChannel = self._node.get_cchannel(next_hop)
            packet = ClassicPacket(msg=msg, src=self._node, dest=next_hop)
            cchannel.send(packet=packet, next_hop=next_hop)
        # sendbb84.change_cur_pool = False


class RecvRoutingApp(Application):
    def __init__(self, net: QuantumNetwork, node: QNode, topo: WaxmanTopology, send_mode: dict, restrict: dict, reject_app_packet_symbol: dict, link_value: dict, bb84_sapps,
                 bb84_rapps, request_management: dict = {}, succ_request: list = [], fail_request: list = [], routing_info: dict = {}):
        super().__init__()
        self.routing_table = routing_info
        self.request_management = request_management
        self.success_request = succ_request
        self.fail_request = fail_request
        self.link_value = link_value
        self.restrict = restrict
        self.temperary_restrict = {}
        self.send_mode = send_mode
        self.recv_msg = {}
        self.reject_app_packet_symbol = reject_app_packet_symbol
        self.routing_coming_node = {}
        self.bb84sapps = bb84_sapps
        self.bb84rapps = bb84_rapps
        self.net = net
        self.topo = topo
        #   self.waiting_queue: dict = {}
        #   for qchannel in node.qchannels:
        #       self.waiting_queue[qchannel.name] = []

    def install(self, node, simulator: Simulator):
        super().install(node, simulator)
        self._simulator = simulator
        self._node = node
        self.add_handler(self.handleClassicPacket, [RecvClassicPacket], [])

    def deal_with_routing(self, msg: str):
        mode = msg["mode"]
        symbol = msg["symbol"]
        dest = self.request_management[symbol]["dest"]
        src = self.request_management[symbol]["src"]
        start_recovery_node = self.net.get_node(msg["RecPosition"])
        if mode == "greedy" or distance(node=self._node, dest=dest, topo=self.topo) < distance(node=start_recovery_node, dest=dest, topo=self.topo):
            # 原本就是greedy或者达到转为greedy的条件
            num, another_dist = send_calculate_link_value(net=self.net, topo=self.topo, node=self._node, symbol=symbol, dest=dest, rapps=self.bb84rapps, restrict=self.restrict, coming_node=self.routing_coming_node[symbol])
            if num > 0:
                mssg = {"symbol": symbol, "type": "finding", "mode": "greedy", "loop": 0, "RecPosition": None, "RecIF": None,
                        "key requirement": msg["key requirement"], "request times": msg["request times"]}
                #   , "request times": self.request_management[symbol]["request times"]
                #   一开始是贪婪模式，不存在恢复模式需要的信息
                self.link_value[symbol] = {}
                self.link_value[symbol]["Mthr list"] = {}
                self.link_value[symbol]["msg"] = mssg
                self.link_value[symbol]["number"] = num
                self.link_value[symbol]["another dist"] = another_dist
                temp = 0    # 计算自己节点的L
                for qchannel in self._node.qchannels:
                    sendbb84, recvbb84 = search_app(self.bb84sapps, self.bb84rapps, qchannel.name)
                    s_curr = sendbb84.current_pool
                    r_curr = recvbb84.current_pool
                    curr = min(s_curr, r_curr)
                    temp += curr
                val = temp / len(self._node.qchannels)
                self.link_value[symbol]["value"] = val
                self.send_mode[symbol] = "greedy"
            else:   # 首次进入recovery模式
                next_hop = search_right_hand(net=self.net, topo=self.topo, node=self._node, dest=dest, rapps=self.bb84rapps, restrict=self.restrict,
                                             coming_node=self.routing_coming_node[symbol], temp_restrict=self.temperary_restrict[symbol], symbol=symbol)
                if next_hop is not None:
                    mssg = {"symbol": symbol, "type": "finding", "mode": "recovery", "loop": 0, "RecPosition": self._node.name, "RecIF": next_hop.name,
                            "key requirement": msg["key requirement"], "request times": msg["request times"]}
                    cchannel: ClassicChannel = self._node.get_cchannel(next_hop)
                    packet = ClassicPacket(msg=mssg, src=self._node, dest=next_hop)
                    cchannel.send(packet=packet, next_hop=next_hop)
                    self.routing_table[dest.name][symbol] = next_hop    # refresh routing table
                    self.send_mode[symbol] = "recovery"
                else:   # 没有可用路径，回退
                    if self._node != src:
                        self.temperary_restrict[symbol] = {}
                        self.send_mode[symbol] = "no"
                        self.routing_table[dest.name][symbol] = None
                        next_hop = self.routing_coming_node[symbol]
                        mssg = {"symbol": symbol, "type": "finding back", "loop": 0, "RecPosition": msg["RecPosition"], "RecIF": msg["RecIF"],
                                "key requirement": msg["key requirement"], "request times": msg["request times"]}
                        cchannel: ClassicChannel = self._node.get_cchannel(next_hop)
                        packet = ClassicPacket(msg=mssg, src=self._node, dest=next_hop)
                        cchannel.send(packet=packet, next_hop=next_hop)
                        #   self.restrict[dest][] = {"dest": dest, "next_hop": another, "time": t_cache, "aim": ["all"]}
                    else:
                        self.request_management[symbol]["request times"] += 1
                        attr = self.request_management[symbol]["attr"]
                        re = Request(src=src, dest=dest, attr=attr)
                        sendapp = self._node.get_apps(SendRoutingApp).pop(0)
                        t = self._simulator.tc + self._simulator.time(sec=time_waiting_resource)
                        event = func_to_event(t, sendapp.send_re_packet, re=re, first_flag=False, symbol=symbol)
                        self._simulator.add_event(event)
        else:   # 继续recovery
            next_hop = search_right_hand(net=self.net, topo=self.topo, node=self._node, dest=dest, rapps=self.bb84rapps,
                                         restrict=self.restrict, coming_node=self.routing_coming_node[symbol], temp_restrict=self.temperary_restrict[symbol], symbol=symbol)
            if next_hop is not None:
                mssg = {"symbol": symbol, "type": "finding", "mode": "recovery", "loop": 0, "RecPosition": msg["RecPosition"], "RecIF": msg["RecIF"],
                        "key requirement": msg["key requirement"], "request times": msg["request times"]}
                cchannel: ClassicChannel = self._node.get_cchannel(next_hop)
                packet = ClassicPacket(msg=mssg, src=self._node, dest=next_hop)
                cchannel.send(packet=packet, next_hop=next_hop)
                self.routing_table[dest.name][symbol] = next_hop
                self.send_mode[symbol] = "recovery"
            else:   # 没有可用路径，回退，不会写路由表，不用更新
                if self._node != src:
                    self.routing_table[dest.name][symbol] = None
                    self.temperary_restrict[symbol] = {}
                    next_hop = self.routing_coming_node[symbol]
                    self.send_mode[symbol] = "no"
                    mssg = {"symbol": symbol, "type": "finding back", "loop": 0, "RecPosition": msg["RecPosition"], "RecIF": msg["RecIF"],
                            "key requirement": msg["key requirement"], "request times": msg["request times"]}
                    cchannel: ClassicChannel = self._node.get_cchannel(next_hop)
                    packet = ClassicPacket(msg=mssg, src=self._node, dest=next_hop)
                    cchannel.send(packet=packet, next_hop=next_hop)
                    #   self.restrict[dest][] = {"dest": dest, "next_hop": another, "time": t_cache, "aim": ["all"]}
                else:
                    self.request_management[symbol]["request times"] += 1
                    attr = self.request_management[symbol]["attr"]
                    re = Request(src=src, dest=dest, attr=attr)
                    sendapp = self._node.get_apps(SendRoutingApp).pop(0)
                    t = self._simulator.tc + self._simulator.time(sec=time_waiting_resource)
                    event = func_to_event(t, sendapp.send_re_packet, re=re, first_flag=False, symbol=symbol)
                    self._simulator.add_event(event)

    def handleClassicPacket(self, node: QNode, event: Event):
        if isinstance(event, RecvClassicPacket):
            packet = event.packet
            # get the packet message
            msg = packet.get()
            #   coming_cchannel = event.cchannel
            msg_type = msg["type"]
            symbol = msg["symbol"]
            dest = self.request_management[symbol]["dest"]
            src = self.request_management[symbol]["src"]
            if msg_type == "finding":
                if dest == self._node:
                    answer: dict = {"symbol": symbol, "type": "finding answer", "answer": "yes"}
                    next_hop = src
                    cchannel: ClassicChannel = self._node.get_cchannel(next_hop)
                    packet = ClassicPacket(msg=answer, src=self._node, dest=next_hop)
                    cchannel.send(packet=packet, next_hop=next_hop)
                else:   # 继续寻路
                    self.recv_msg[symbol] = msg
                    if self.send_mode.get(symbol) is None or self.send_mode[symbol] == "no":  # 还没有对其进行路由过或者退回去了
                        self.temperary_restrict[symbol] = {}
                        self.routing_coming_node[symbol] = packet.src   # 记录一下，防止后面回退找不到节点
                        self.deal_with_routing(msg=msg)
                    else:   # 不能再经过这个节点，会形成环路
                        mssg = {"symbol": symbol, "type": "finding back", "recycle": True, "loop": 0, "RecPosition": msg["RecPosition"], "RecIF": msg["RecIF"],
                                "key requirement": msg["key requirement"], "request times": msg["request times"]}
                        next_hop = packet.src
                        cchannel: ClassicChannel = self._node.get_cchannel(next_hop)
                        packet = ClassicPacket(msg=mssg, src=self._node, dest=next_hop)
                        cchannel.send(packet=packet, next_hop=next_hop)
            elif msg_type == "finding back":    # 回退回来的包
                temp = packet.src
                route_list = self.net.query_route(src=temp, dest=dest)
                if len(route_list) > 0:
                    route = route_list[0]
                    hop = route[0]
                else:
                    hop = float('inf')
                t_cache = self._simulator.tc.time_slot + hop * ((c_length * 2 + q_length) / light_speed + 1 / accuracy) * accuracy
                #  distance(node=temp, dest=dest)
                if msg.get("recycle") is True:
                    if self.temperary_restrict.get(symbol) is None:
                        self.temperary_restrict[symbol] = {}
                    self.temperary_restrict[symbol][temp.name] = True    # greedy 不会出现环路
                else:
                    self.restrict[temp.name][dest.name] = {"distance": distance(temp, dest, self.topo)/2, "time": t_cache}
                self.routing_table[dest.name][symbol] = None    # 去掉原来的路由表信息
                # go_on_mode = self.send_mode[symbol]
                # flag = False
                # if src != self._node:
                #     if self.recv_mode[symbol] == "greedy":
                #         flag = True
                # else:
                #     flag = True
                # if (go_on_mode == "greedy" and flag) or msg["RecPosition"] == self._node:
                #     mssg = {"symbol": symbol, "type": "finding", "mode": "greedy", "loop": 0, "RecPosition": None, "RecIF": None,
                #             "key requirement": msg["key requirement"], "request times": msg["request times"]}
                # elif go_on_mode == "greedy" and self.recv_mode[symbol] == "recovery":
                #     mssg = {"symbol": symbol, "type": "finding", "mode": "recovery", "loop": 0, "RecPosition": self.recv_become_greedy_msg[symbol], "RecIF": msg["RecIF"],
                #             "key requirement": msg["key requirement"], "request times": msg["request times"]}
                # else:
                #     mssg = {"symbol": symbol, "type": "finding", "mode": "recovery", "loop": 0, "RecPosition": msg["RecPosition"], "RecIF": msg["RecIF"],
                #             "key requirement": msg["key requirement"], "request times": msg["request times"]}
                if src == self._node:
                    self.request_management[symbol]["request times"] += 1
                    attr = self.request_management[symbol]["attr"]
                    re = Request(src=src, dest=dest, attr=attr)
                    sendapp = self._node.get_apps(SendRoutingApp).pop(0)
                    event = func_to_event(self._simulator.tc, sendapp.send_re_packet, re=re, first_flag=False, symbol=symbol)
                    self._simulator.add_event(event)
                else:
                    mssg = self.recv_msg[symbol]
                    self.link_value[symbol] = {}
                    self.deal_with_routing(msg=mssg)    # 重新寻路
            elif msg_type == "finding answer":
                if self.request_management[symbol]["state"] == "finding":
                    answer = msg["answer"]
                    if answer == "yes":     # 寻路成功(dest send)即发包
                        packet_src = packet.src
                        if packet_src == dest:
                            key_requirement = self.request_management[symbol]["attr"].get("key requirement")
                            self.request_management[symbol]["state"] = "routing"
                            tc_slot = self._simulator.tc.time_slot
                            self.request_management[symbol]["start routing"] = tc_slot
                            print("start routing: ", self.request_management[symbol])
                            order = 0
                            #   info: dict = {}
                            #   info["symbol"] = symbol
                            #   info["src"] = src
                            #   info["dest"] = dest
                            #   info["delay"] = self.request_management[symbol]["attr"].get("delay")
                            delay = self.request_management[symbol]["attr"].get("delay")
                            #   sendapp = self._node.get_apps(SendRoutingApp).pop(0)
                            next_hop = self.routing_table[dest.name][symbol]
                            qchannel: QuantumChannel = self._node.get_qchannel(next_hop)
                            sendbb84, recvbb84 = search_app(self.bb84sapps, self.bb84rapps, qchannel.name)
                            if sendbb84.get_node() == self._node:     # 保证在自己的节点上面排队
                                app = sendbb84
                            elif recvbb84.get_node() == self._node:
                                app = recvbb84
                            while key_requirement > 0:  # 发送数据包
                                order += 1
                                if key_requirement >= packet_length:
                                    mssg = {"symbol": symbol, "type": "routing", "order": order, "length": packet_length,
                                            "start routing time": self.request_management[symbol]["start routing"], "delay": delay}
                                    #   event = func_to_event(self._simulator.tc, sendapp.send_app_packet, info=info, order=order, data_packet_length=packet_length, first_node=True)   # , None, None
                                    key_requirement -= packet_length
                                    app.waiting_length_queue.append(packet_length)
                                else:
                                    app.waiting_length_queue.append(key_requirement)
                                    mssg = {"symbol": symbol, "type": "routing", "order": order, "length": key_requirement,
                                            "start routing time": self.request_management[symbol]["start routing"], "delay": delay}
                                    #   event = func_to_event(self._simulator.tc, sendapp.send_app_packet, info=info, order=order, data_packet_length=key_requirement, first_node=True)
                                    key_requirement = 0
                                #   self._simulator.add_event(event)
                                app.waiting_msg_queue.append(mssg)
            elif msg_type == "routing":
                order = msg["order"]
                if dest == self._node:  # 给源端反馈
                    answer: dict = {"symbol": symbol, "type": "routing answer", "answer": "yes", "order": order, "receiving time": self._simulator.tc.time_slot}
                    next_hop = src
                    cchannel: ClassicChannel = self._node.get_cchannel(next_hop)
                    packet = ClassicPacket(msg=answer, src=self._node, dest=next_hop)
                    cchannel.send(packet=packet, next_hop=next_hop)
                else:
                    if self.reject_app_packet_symbol.get(symbol) is None:
                        #   前序包均已在此链路上路由成功，没有超过延时
                        length = msg["length"]
                        next_hop = self.routing_table[dest.name][symbol]
                        qchannel: QuantumChannel = self._node.get_qchannel(next_hop)
                        sendbb84, recvbb84 = search_app(self.bb84sapps, self.bb84rapps, qchannel.name)
                        if sendbb84.get_node() == self._node:
                            app = sendbb84
                        elif recvbb84.get_node() == self._node:
                            app = recvbb84
                        app.waiting_length_queue.append(length)
                        app.waiting_msg_queue.append(msg)
            elif msg_type == "routing answer":  # is sent by dest
                if self.request_management[symbol]["state"] == "routing":
                    order = msg["order"]
                    if self.request_management[symbol]["packet arrival"].get(order) is None:
                        answer = msg["answer"]
                        if answer == "yes":
                            self.request_management[symbol]["packet arrival"][order] = True
                            if len(self.request_management[symbol]["packet arrival"]) == self.request_management[symbol]["packet number"]:
                                self.request_management[symbol]["end routing"] = msg["receiving time"]
                                self.request_management[symbol]["state"] = "successful"
                                attr: dict = self.request_management[symbol]["attr"]
                                re = Request(src=src, dest=dest, attr=attr)
                                self.success_request.append(re)
                        elif answer == "no":
                            self.request_management[symbol]["state"] = "failed"
                            attr: dict = self.request_management[symbol]["attr"]
                            re = Request(src=src, dest=dest, attr=attr)
                            self.fail_request.append(re)
            elif msg_type == "calculation":
                temp = 0
                for qchannel in self._node.qchannels:
                    sendbb84, recvbb84 = search_app(self.bb84sapps, self.bb84rapps, qchannel.name)
                    s_curr = sendbb84.current_pool
                    r_curr = recvbb84.current_pool
                    curr = min(s_curr, r_curr)
                    temp += curr
                val = temp / len(self._node.qchannels)
                mssg = {"type": "calculation answer", "symbol": symbol, "answer": val}
                next_hop = packet.src
                c: ClassicChannel = self._node.get_cchannel(next_hop)
                p = ClassicPacket(msg=mssg, src=self._node, dest=next_hop)
                c.send(packet=p, next_hop=next_hop)
            elif msg_type == "calculation answer":
                answer = msg["answer"]
                qchannel: QuantumChannel = self._node.get_qchannel(packet.src)
                self.link_value[symbol]["Mthr list"][qchannel.name] = answer
                if self.link_value[symbol]["number"] == len(self.link_value[symbol]["Mthr list"]):
                    event = func_to_event(self._simulator.tc, search_next_hop, net=self.net, node=self._node, dest=dest, routing_table=self.routing_table, simulator=self._simulator,
                                          info=self.link_value[symbol], sapps=self.bb84sapps, rapps=self.bb84rapps)
                    self._simulator.add_event(event=event)
