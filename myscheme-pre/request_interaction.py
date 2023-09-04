from qns.entity.node.app import Application
from qns.entity.node.node import QNode
from qns.entity.cchannel.cchannel import ClassicChannel, ClassicPacket, RecvClassicPacket
from qns.entity.qchannel.qchannel import QuantumChannel
from qns.simulator.event import func_to_event, Event
from qns.simulator.simulator import Simulator
from qns.simulator.ts import Time
from qns.network.requests import Request
from qns.network.network import QuantumNetwork


# def classify_request(net: QuantumNetwork):
# 将网络内的随机请求分类给对应的源节点(直接在产生请求的时候就把请求加入到对应源节点的请求队列中)
#    request_lists: list[Request] = net.requests
#    for re in request_lists:
#        src = re.src
#        index = int(src.name[1])
#        net.nodes[index].requests.append(re)
event_trigger = 5
accuracy = 3000  # {default_accuracy} time slots per second
time_trigger = 0.01    # second
request_times_restrict = 10
#   packet_length = 20
waiting_resource_time = 0.1
max_routing_times = 500
send_rate = 3000


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


def out_delay(qchannel: QuantumChannel, restrict_time: dict, delay: float):
    # 判断限制是否真的无法满足请求，定时器
    flag = False
    t = restrict_time[qchannel.name]
    s = qchannel._simulator
    if t < s.tc.time_slot:
        return flag
    time_span = t - s.tc.time_slot
    if time_span > delay * accuracy:
        flag = True
    return flag


# def restrict_is_real(qchannel: QuantumChannel, restrict_time: dict):
#     t = restrict_time[qchannel.name]
#     s = qchannel._simulator
#     if t < s.tc.time_slot:
#         return False
#     return True


# def has_no_restrict(path: tuple[float, QNode, list[QNode]], restrict: dict, restrict_time: dict):
#     # 判断路径上是否存在限制link
#     flag = True
#     for i in range(0, len(path[2])-1):
#         qchannel: QuantumChannel = path[2][i].get_qchannel(path[2][i+1])
#         result = restrict[qchannel.name]    # 返回是否存在限制
#         if result and restrict_is_real(qchannel, restrict_time):
#             flag = False
#             break
#     return flag


def check_realizable(path: tuple[float, QNode, list[QNode]], restrict: dict, restrict_time: dict, delay: float):
    # 判断此条路径是否可行（是否存在不符合请求要求的link）
    flag = True
    for i in range(0, len(path[2])-1):
        qchannel: QuantumChannel = path[2][i].get_qchannel(path[2][i+1])
        result = restrict.get(qchannel.name)    # 返回是否存在限制
        if result and out_delay(qchannel, restrict_time, delay):
            flag = False
            break
    return flag


def if_already_in(already_accept: list[dict], item: dict):
    flag = False
    for i in already_accept:
        if item == i:
            flag = True
            break
    return flag


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


def get_info(send_app):    # 返回pool速率以及time
    s: Simulator = send_app.get_simulator()
    # ts = s.ts
    tc = s.tc
    rate = send_rate
    time = send_app.time_flag
    if time < tc.time_slot and (tc.time_slot - time) * rate / accuracy > send_app.pool_capacity:
        send_app.time_flag = tc.time_slot - (send_app.pool_capacity / rate * accuracy)
    # if time < tc.time_slot:
    #     time = tc.time_slot
    #   time_span = time - tc.time_slot
    return rate, send_app.time_flag
    #   , time_span


def get_qchannel_list(node: QNode):
    link: list[QuantumChannel] = node.qchannels
    return link


def initialize(qchannels: list[QuantumChannel]):
    event = {}
    time = {}
    queue = {}
    first_time_strigger = {}
    for qchannel in qchannels:
        event[qchannel.name] = 0
        time[qchannel.name] = []    # 表示收到的请求的到达时间
        queue[qchannel.name] = []
        first_time_strigger[qchannel.name] = True   # 'first' request
    return event, time, queue, first_time_strigger


def queue_sort(queue: list):
    queue.sort(key=lambda s: s["key requirement"], reverse=True)    # from big to small and is stable
    queue.sort(key=lambda s: s["delay"])
    queue_up_times: list = []
    queue_down_times: list = []
    for item in queue:
        temp = item["request times"]
        if temp < request_times_restrict:
            queue_down_times.append(item)
        else:
            queue_up_times.append(item)
    queue_up_times.sort(key=lambda s: s["request times"], reverse=True)     # 没超过阈值，不需要按照路由次数排序
    if len(queue_up_times) > 0 and len(queue_down_times) > 0:
        queue_up_times.extend(queue_down_times)
        sorted_queue = queue_up_times
    elif len(queue_down_times) > 0:
        sorted_queue = queue_down_times
    else:
        sorted_queue = queue_up_times
    return sorted_queue


def create_request_info(management: dict, symbol: str, path_list: list[tuple[float, QNode, list[QNode]]], index: int, re: Request):
    temp: dict = {}
    temp["flag"] = True     # 正常接收link的反馈，false代表此路径已不可行，对于answer“yes”，及时发包delete
    temp["list"] = []
    temp["re"] = re
    temp["path list"] = path_list
    temp["path index"] = index
    # temp["start routing"] = 0
    # temp["end routing"] = 0
    # temp["packet arrival"] = {}
    # temp["packet number"] = 0
    management[symbol] = temp


def update_request_info(node: QNode, management: dict, symbol: str):     # 把已经预留资源的链路取消锁定
    for item in management[symbol]["list"]:
        src: QNode = item["src"]
        qchannel_name = item["aimed qchannel"]
        key_requirement = item["key requirement"]
        packet = ClassicPacket(msg={"aim": "delete", "symbol": symbol, "aimed qchannel": qchannel_name, "key requirement": key_requirement}, src=node, dest=src)
        cchannel: ClassicChannel = src.get_cchannel(node)     # route.query(node, src)
        cchannel.send(packet=packet, next_hop=src)
    management[symbol]["list"] = []


def check_if_is_over(mess: dict):
    flag = False
    index = mess["path index"]
    path_list = mess["path list"]
    if mess["flag"] and len(mess["list"]) == len(path_list[index][2])-1:
        temp = {}
        path = path_list[index]
        for i in range(0, len(path[2])-1):
            qchannel: QuantumChannel = path[2][i].get_qchannel(path[2][i+1])
            temp[qchannel.name] = False
        for item in mess["list"]:
            qchannel_name = item["aimed qchannel"]
            temp[qchannel_name] = True
        for item in temp.values():
            if item is False:
                return flag
        flag = True
    return flag


class SendRequestApp(Application):
    def __init__(self, node: QNode, net: QuantumNetwork, bb84rapps: list, bb84sapps: list, restrict: dict, restrict_time: dict, request_management: dict, fail_request: list[Request] = [], request_list: list[Request] = []):
        # , request_list: list[Request] = []
        # 这里是量子网络的路由表， restrict代表当前节点维护的拓扑的限制信息, time slot
        super().__init__()
        self.request_list = request_list
        self.fail_request = fail_request
        self.connect_bb84sapps = bb84sapps
        self.connect_bb84rapps = bb84rapps
        #   print(re.attr for re in node.requests)
        self.request_management = request_management
        self.restrict = restrict
        self.restrict_time = restrict_time
        self.routing_table = {}
        self.net = net
        self.reject_app_packet_symbol = {}
        self.consume_key = 0
        self.count = 0

    def install(self, node: QNode, simulator: Simulator):
        super().install(node, simulator)
        # self.request_list.sort(Request.attr["start time"])
        self._simulator = simulator
        self._node = node
        if len(self.request_list) > 0:
            re = self.request_list.pop(0)
            temp = re.attr["start time"]
            t = temp+simulator.ts
            # print(re.attr, t)
            event = func_to_event(t, self.send_packet, re=re)
            self._simulator.add_event(event)

    def send_packet(self, re: Request, first_send: bool = True, sym_former: str = ""):
        if len(self.request_list) > 0:
            r = self.request_list.pop(0)
            temp = r.attr["start time"]
            t = temp + self._simulator.ts
            # print(re.attr, t)
            event = func_to_event(t, self.send_packet, re=r)
            self._simulator.add_event(event)
        src = re.src
        dest = re.dest
        attr = re.attr
        if attr["request times"] > max_routing_times:   # 无法服务``
            print(f"{src.name}->{dest.name} is failed in serving currently(too many tries): {attr}")
            self.fail_request.append(re)
            return
        flag = False    # 是否有路径可以尝试发送
        #   print(re.src, re.dest, re.attr["start time"],  route_result)
        # count = True
        # index = float("inf")
        # i = 0
        # while i < len(route_result):  # 筛选出所有可行最短路径choice
        #     if route_result[i][0] > index:
        #         break
        #     if not check_realizable(route_result[i], self.restrict, self.restrict_time, attr["delay"]):  # 不可行
        #         del route_result[i]
        #         continue
        #     if count:
        #         index = route_result[i][0]  # 可行的最短路径长度
        #         count = False
        #     i += 1
        # signal = False  # 是否找到目标路径
        # for item in route_result:
        #     if item[0] > index:
        #         break
        #     if has_no_restrict(item, self.restrict, self.restrict_time):    # 存在一条没有限制的最短路径
        #         path = item
        #         flag = True
        #         signal = True
        #         break
        # if not signal and len(route_result) > 0:
        #     flag = True
        #     path = route_result[0]
        symbol = f"{self.get_node().name}-{self.count}"
        if first_send:
            start = 0
            route_result = self.net.query_route(src, dest)
            if len(route_result) == 0:
                print(f"{src.name}->{dest.name} is failed in serving currently: {attr}")
                self.fail_request.append(re)
                return
        else:
            route_result = self.request_management[sym_former]["path list"]
            start = (self.request_management[sym_former]["path index"] + 1) % len(route_result)
        path = None
        i = start
        while True:
            if check_realizable(route_result[i], self.restrict, self.restrict_time, attr["delay"]):
                flag = True
                path = route_result[i]
                break
            i = (i + 1) % len(route_result)
            if i == start:
                break
        if not flag:    # 没有路径可尝试
            t = self._simulator.tc + Time(sec=waiting_resource_time)
            attr["request times"] += 1
            if not first_send:
                event = func_to_event(t, self.send_packet, re=re, first_send=False, sym_former=sym_former)   # , None, None
            else:
                event = func_to_event(t, self.send_packet, re=re)
            self._simulator.add_event(event)
            return
        print("routing:", re, re.attr)
        create_request_info(self.request_management, symbol, route_result, i, re)
        path_list: list = path[2]
        for i in range(1, len(path_list)):
            # 中间节点，假设经典网络是.all，请求信息均可一跳到达
            next_hop = path_list[i]     # next_hop = self.route.query(re.src, path_list[i])[0][1]
            cchannel: ClassicChannel = src.get_cchannel(next_hop)    # 找到传请求需要的经典link
            qchannel: QuantumChannel = path_list[i].get_qchannel(path_list[i-1])    # 找到需要预留资源的量子link
            packet = ClassicPacket(msg={"aim": "require", "symbol": symbol, "aimed qchannel": qchannel.name,  # f"{path_list[i-1].name}-{next_hop.name}",
                                        "key requirement": attr["key requirement"], "delay": attr["delay"], "request times": attr["request times"]}, src=src, dest=next_hop)   # dest=path_list[i]
            cchannel.send(packet=packet, next_hop=next_hop)
        self.count += 1

    def send_app_packet(self, info: dict, qchannel: QuantumChannel):
        #   , order: int, data_packet_length: int = 0, first_node: bool = True
        #   length stands for single key requirement
        sym = info["symbol"]
        #   dest_name = info["dest"]
        next_hop = self.routing_table[sym]
        #   qchannel: QuantumChannel = self._node.get_qchannel(next_hop)
        sendbb84, recvbb84 = search_app(self.connect_bb84sapps, self.connect_bb84rapps, qchannel.name)
        # 两者之间最多差一个bit，存在min key，不会有只有一个达到密钥量的情况、send大于，recv不小于
        if info["delay"] * accuracy + info["start routing time"] > self._simulator.tc.time_slot:
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
            msg = {"symbol": sym, "aim": "routing answer", "answer": "no", "order": info["order"]}
            index = self.request_management[sym]["path index"]
            path_list = self.request_management[sym]["path list"]
            next_hop = path_list[index][2][0]
            cchannel: ClassicChannel = self._node.get_cchannel(next_hop)
            packet = ClassicPacket(msg=msg, src=self._node, dest=next_hop)
            cchannel.send(packet=packet, next_hop=next_hop)


class RecvRequestApp(Application):
    def __init__(self, net: QuantumNetwork, node: QNode, bb84rapps: list, bb84sapps: list, restrict: dict, restrict_time: dict, request_management: dict, already_accept: list = [], fail_request: list[Request] = [], succ_request: list = []):
        # 已经接受可服务的，预留资源了
        super().__init__()
        self.net = net
        self.already_accept = already_accept
        self.connect_bb84rapps = bb84rapps  # 知道与节点连接的所有link信息即可
        self.connect_bb84sapps = bb84sapps
        self.restrict = restrict
        self.restrict_time = restrict_time
        self.request_management = request_management
        self.succ_request = succ_request
        self.fail_request = fail_request

    def install(self, node: QNode, simulator: Simulator):   # 为每条qchannel创建初始时间触发事件xxxxxxxxxxx  no need  first packet begin is ok
        self.qchannels = get_qchannel_list(node)
        self.event_number_list, self.time_info, self.queue_list, self.first_time_strigger = initialize(self.qchannels)
        #   event strigger  time strigger  request queueing   'first' strigger
        self.add_handler(self.handleClassicPacket, [RecvClassicPacket], [])
        #   t = simulator.ts
        #   str_t = t+Time(sec=time_trigger)
        self._simulator = simulator
        self._node = node
        #   for qchannel in self.qchannels:
        #    event = func_to_event(str_t, self.handletimer, qchannel_name=qchannel.name)   # None, None,
        #    simulator.add_event(event)

    def distribution(self, queue: list, qchannel_name: str):
        sorted_queue = queue_sort(queue)
        for item in sorted_queue:
            #   print("processing:", item)
            key_requirement = item["key requirement"]
            delay_tolerance = item["delay"]
            send_bb84, recv_bb84 = search_app(self.connect_bb84sapps, self.connect_bb84rapps, qchannel_name)
            assert (send_bb84 is not None)
            assert (recv_bb84 is not None)
            rate, time_flag = get_info(send_bb84)
            # while len(send_bb84.release_key_queue) > 0:
            #     key_num = send_bb84.release_key_queue.pop(0)
            #     back_time = key_num / rate * accuracy
            #     min_time_flag = self._simulator.tc.time_slot - send_bb84.pool_capacity / rate * accuracy
            #     future_time_flag = time_flag - back_time
            #     if future_time_flag < min_time_flag:
            #         send_bb84.time_flag = min_time_flag
            #         send_bb84.release_key_queue = []
            #         break
            #         # simulator: Simulator = self._simulator
            #         # send_bb84.time_flag = simulator.tc.time_slot
            #         # increase = math.floor(rate*(back_time-time_span)/accuracy)
            #         # if increase < send_bb84.pool_capacity:
            #         #     send_bb84.current_pool += increase
            #         #     recv_bb84.current_pool += increase
            #         # else:
            #         #     send_bb84.current_pool = send_bb84.pool_capacity
            #         #     recv_bb84.current_pool = recv_bb84.pool_capacity
            #     else:
            #         send_bb84.time_flag = future_time_flag
            # time_flag = send_bb84.time_flag
            sig = False
            # cur_pool = send_bb84.current_pool
            # if key_requirement <= cur_pool:  # 先看密钥池中的是否可以满足
            #     recv_bb84.current_pool -= key_requirement
            #     send_bb84.current_pool -= key_requirement
            #     sig = True
            # else:
            #     key_requirement_temp = key_requirement - cur_pool
            #     # 再看考虑未来产生的密钥
            #     rate, time_flag, time_span = get_info(send_bb84)
            #     max_key = rate*(delay_tolerance - time_span/accuracy)
            #     if key_requirement_temp <= max_key:  # 更新time_flag
            #         recv_bb84.current_pool = 0
            #         send_bb84.current_pool = 0
            #         sig = True
            #         t = key_requirement_temp / rate * accuracy
            #         send_bb84.time_flag = t + time_flag
            future_time_flag = time_flag + key_requirement / rate * accuracy
            if future_time_flag < self._simulator.tc.time_slot + delay_tolerance * accuracy:
                send_bb84.time_flag = future_time_flag
                sig = True
            aim_msg = "answer"
            sym_msg: str = item["symbol"]
            request_times = item["request times"]
            # sym = sym_msg.split("-")
            # node_name = sym[0]
            src_node: QNode = item["src"]
            if sig:
                qchannel = self.net.get_qchannel(qchannel_name)
                node_list = qchannel.node_list
                if self._node == node_list[0]:
                    another = node_list[1]
                else:
                    another = node_list[0]
                sendapp = another.get_apps(SendRequestApp).pop(0)
                sendapp.routing_table[sym_msg] = self._node
                self.already_accept.append({sym_msg: qchannel_name})     # 加入到接受列表中
                content = "yes"
                packet = ClassicPacket(msg={"aim": aim_msg, "content": content, "symbol": sym_msg, "aimed qchannel": qchannel_name, "key requirement": key_requirement, "delay": delay_tolerance,
                                            "request times": request_times}, src=self._node, dest=src_node)
            else:
                content = "no"
                packet = ClassicPacket(msg={"aim": aim_msg, "content": content, "symbol": sym_msg, "aimed qchannel": qchannel_name, "key requirement": key_requirement, "delay": delay_tolerance,
                                            "request times": request_times, "time flag": time_flag}, src=self._node, dest=src_node)
            # next_hop = route.query(recv_bb84._node, src)
            next_hop = src_node
            cchannel: ClassicChannel = src_node.get_cchannel(self._node)
            cchannel.send(packet=packet, next_hop=next_hop)
            #     if len(send_bb84.time_flag_queue) > 0:
            #         temp = send_bb84.time_flag_queue.pop(0)
            #         node = temp["node"]
            #         queue = temp["queue"]
            #         qchannel_name = temp["qchannel name"]
            #         recv_app = node.get_apps(RecvRequestApp).pop(0)
            #         event = func_to_event(self._simulator.tc, recv_app.distribution, by=node, queue=queue, qchannel_name=qchannel_name)
            #         self._simulator.add_event(event)
            # else:
            #     temp: dict = {}
            #     temp["node"] = self._node
            #     temp["queue"] = queue
            #     temp["qchannel name"] = qchannel_name
            #     send_bb84.time_flag_queue.append(temp)

    def handletimer(self, qchannel_name: str):
        if len(self.time_info[qchannel_name]) > 0:
            self.time_info[qchannel_name].pop(0)
        else:
            if self.event_number_list[qchannel_name] > 0:
                self.event_number_list[qchannel_name] = 0
                queue = self.queue_list[qchannel_name]
                self.queue_list[qchannel_name] = []
                self.distribution(queue, qchannel_name)
            self.first_time_strigger[qchannel_name] = True

    def handleClassicPacket(self, node: QNode, event: Event):
        # receive a classic packet，假设目的节点就是本节点，否则被前方的app转发走了
        if isinstance(event, RecvClassicPacket):
            packet = event.packet
            # get the packet message
            msg = packet.get()
            recv_time = event.t
            # handling the receiving packet
            aim_msg = msg.get("aim")
            sym_msg = msg.get("symbol")
            qchannel_name = msg.get("aimed qchannel")
            request_times = msg.get("request times")
            key_requirement = msg.get("key requirement")
            delay_tolerance = msg.get("delay")
            src = packet.src
            if aim_msg == "require":    # 中间节点
                flag = if_already_in(self.already_accept, {sym_msg: qchannel_name})   # 是否已经在准备服务的名单里
                if not flag:
                    temp: dict = {"symbol": sym_msg, "aimed qchannel": qchannel_name, "key requirement": key_requirement, "delay": delay_tolerance, "request times": request_times, "src": src}
                    self.queue_list[qchannel_name].append(temp)
                    self.event_number_list[qchannel_name] += 1
                    if self.first_time_strigger.get(qchannel_name) is True:
                        self.first_time_strigger[qchannel_name] = False
                    else:
                        self.time_info[qchannel_name].append(recv_time)
                    t = recv_time + Time(sec=time_trigger)    # 加入对应时间触发事件
                    strigger = func_to_event(t, self.handletimer, qchannel_name=qchannel_name)    # , None, None
                    s = self._simulator
                    s.add_event(strigger)
                    if self.event_number_list[qchannel_name] == event_trigger:  # 检查事件触发
                        self.event_number_list[qchannel_name] = 0
                        queue = self.queue_list[qchannel_name]
                        self.queue_list[qchannel_name] = []
                        self.distribution(queue, qchannel_name)
            elif aim_msg == "answer":   # 源节点
                content = msg.get("content")
                if content == "yes":
                    # 先加入链路同意的列表，判断整条路径上的链路均同意了，再加入到already_accept
                    stamp = self.request_management[sym_msg]
                    if stamp.get("flag"):
                        mass: dict = {"aimed qchannel": qchannel_name, "request times": request_times, "key requirement": key_requirement, "delay": delay_tolerance, "src": src}
                        stamp["list"].append(mass)
                        flag = check_if_is_over(self.request_management[sym_msg])
                        if flag:
                            # index = stamp["path index"]
                            # path_list = stamp["path list"]
                            # path = path_list[index][2]
                            # dest = path[-1]
                            # attr: dict = {"key requirement": key_requirement, "delay": delay_tolerance, "request times": request_times}
                            self.succ_request.append(sym_msg)
                            # tc_slot = self._simulator.tc.time_slot
                            # self.request_management[sym_msg]["start routing"] = tc_slot
                            # self.request_management[sym_msg]["packet number"] = math.ceil(key_requirement / packet_length)
                            # #   print("start routing: ", self.request_management[sym_msg])
                            # order = 0
                            # #   sendapp = self._node.get_apps(SendRoutingApp).pop(0)
                            # next_hop = path[1]
                            # qchannel: QuantumChannel = self._node.get_qchannel(next_hop)
                            # sendbb84, recvbb84 = search_app(self.connect_bb84sapps, self.connect_bb84rapps, qchannel.name)
                            # if sendbb84.get_node() == self._node:     # 保证在自己的节点上面排队
                            #     app = sendbb84
                            # elif recvbb84.get_node() == self._node:
                            #     app = recvbb84
                            # while key_requirement > 0:  # 发送数据包
                            #     order += 1
                            #     if key_requirement >= packet_length:
                            #         mssg = {"symbol": sym_msg, "aim": "routing", "order": order, "length": packet_length, "dest": dest.name, "src": self._node.name,
                            #                 "start routing time": self.request_management[sym_msg]["start routing"], "delay": delay_tolerance}
                            #         #   event = func_to_event(self._simulator.tc, sendapp.send_app_packet, info=info, order=order, data_packet_length=packet_length, first_node=True)   # , None, None
                            #         key_requirement -= packet_length
                            #         app.waiting_length_queue.append(packet_length)
                            #     else:
                            #         app.waiting_length_queue.append(key_requirement)
                            #         mssg = {"symbol": sym_msg, "aim": "routing", "order": order, "length": key_requirement, "dest": dest.name, "src": self._node.name,
                            #                 "start routing time": self.request_management[sym_msg]["start routing"], "delay": delay_tolerance}
                            #         #   event = func_to_event(self._simulator.tc, sendapp.send_app_packet, info=info, order=order, data_packet_length=key_requirement, first_node=True)
                            #         key_requirement = 0
                            #     #   self._simulator.add_event(event)
                            #     app.waiting_msg_queue.append(mssg)
                            # print(self.succ_request)
                    else:       # 此路径不可行，立即让其释放资源
                        packet = ClassicPacket(msg={"aim": "delete", "symbol": sym_msg, "aimed qchannel": qchannel_name, "key requirement": key_requirement}, src=self._node, dest=src)
                        cchannel: ClassicChannel = src.get_cchannel(self._node)     # route.query(self._node, src)
                        cchannel.send(packet=packet, next_hop=src)
                elif content == "no":
                    # update restrict in sendrequestapp and release resource of other agreed links
                    time = msg["time flag"]
                    simulator: Simulator = self._simulator
                    if self.restrict[qchannel_name] is True:
                        if self.restrict_time[qchannel_name] < time:
                            self.restrict_time[qchannel_name] = time
                    else:
                        self.restrict[qchannel_name] = True
                        self.restrict_time[qchannel_name] = time
                    stamp = self.request_management[sym_msg]
                    if stamp.get("flag"):
                        # index = stamp["path index"]
                        # path_list = stamp["path list"]
                        # path = path_list[index]
                        # dest = path[2][-1]
                        self.request_management[sym_msg]["flag"] = False
                        start_time = simulator.tc + Time(sec=waiting_resource_time)
                        # request_times += 1
                        #   attr: dict = {"start time": start_time, "key requirement": key_requirement, "delay": delay_tolerance, "request times": request_times}
                        re = self.request_management[sym_msg]["re"]
                        re.attr["request times"] += 1
                        #   Request(src=self._node, dest=dest, attr=attr)
                        node: QNode = self._node
                        app: Application = node.get_apps(SendRequestApp).pop(0)
                        event = func_to_event(start_time, app.send_packet, re=re, first_send=False, sym_former=sym_msg)   # , None, None
                        simulator.add_event(event)
                        update_request_info(self._node, self.request_management, sym_msg)
            elif aim_msg == "delete":
                if if_already_in(self.already_accept, {sym_msg: qchannel_name}):
                    self.already_accept.remove({sym_msg: qchannel_name})
                    send_bb84, recv_bb84 = search_app(self.connect_bb84sapps, self.connect_bb84rapps, qchannel_name)    # time_flag and capacity
                    # if send_bb84.change_time_flag is False:
                    #     send_bb84.change_time_flag = True
                    rate, time_flag = get_info(send_bb84)
                    back_time = key_requirement / rate * accuracy
                    min_time_flag = self._simulator.tc.time_slot - send_bb84.pool_capacity / rate * accuracy
                    future_time_flag = time_flag - back_time
                    if future_time_flag < min_time_flag:
                        send_bb84.time_flag = min_time_flag
                        # simulator: Simulator = self._simulator
                        # send_bb84.time_flag = simulator.tc.time_slot
                        # increase = math.floor(rate*(back_time-time_span)/accuracy)
                        # if increase < send_bb84.pool_capacity:
                        #     send_bb84.current_pool += increase
                        #     recv_bb84.current_pool += increase
                        # else:
                        #     send_bb84.current_pool = send_bb84.pool_capacity
                        #     recv_bb84.current_pool = recv_bb84.pool_capacity
                    else:
                        send_bb84.time_flag = future_time_flag
                        #   send_bb84.time_flag = cur_time_tolerance - back_time
                        # send_bb84.change_time_flag = False
                    # else:
                    #     send_bb84.release_key_queue.append(key_requirement)
            # elif aim_msg == "routing":
            #     order = msg["order"]
            #     if msg["dest"] == self._node.name:  # 给源端反馈
            #         answer: dict = {"symbol": sym_msg, "aim": "routing answer", "answer": "yes", "order": order, "receiving time": self._simulator.tc.time_slot}
            #         next_hop = self.net.get_node(msg["src"])
            #         cchannel: ClassicChannel = self._node.get_cchannel(next_hop)
            #         packet = ClassicPacket(msg=answer, src=self._node, dest=next_hop)
            #         cchannel.send(packet=packet, next_hop=next_hop)
            #     else:
            #         sendre = self._node.get_apps(SendRequestApp).pop(0)
            #         if sendre.reject_app_packet_symbol.get(sym_msg) is None:
            #             #   前序包均已在此链路上路由成功，没有超过延时
            #             length = msg["length"]
            #             next_hop = sendre.routing_table[sym_msg]
            #             qchannel: QuantumChannel = self._node.get_qchannel(next_hop)
            #             sendbb84, recvbb84 = search_app(self.connect_bb84sapps, self.connect_bb84rapps, qchannel.name)
            #             if sendbb84.get_node() == self._node:
            #                 app = sendbb84
            #             elif recvbb84.get_node() == self._node:
            #                 app = recvbb84
            #             app.waiting_length_queue.append(length)
            #             app.waiting_msg_queue.append(msg)
            # elif aim_msg == "routing answer":  # is sent by dest
            #     order = msg["order"]
            #     if self.request_management[sym_msg]["packet arrival"].get(order) is None:
            #         answer = msg["answer"]
            #         if answer == "yes":
            #             self.request_management[sym_msg]["packet arrival"][order] = True
            #             if len(self.request_management[sym_msg]["packet arrival"]) == self.request_management[sym_msg]["packet number"]:
            #                 self.request_management[sym_msg]["end routing"] = msg["receiving time"]
            #                 re = self.request_management[sym_msg]["re"]
            #                 self.succ_request.append(re)
            #         elif answer == "no":
            #             re = self.request_management[sym_msg]["re"]
            #             self.fail_request.append(re)
