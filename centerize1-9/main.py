from qns.network.network import QuantumNetwork
from bb84 import BB84RecvApp, BB84SendApp
from routing import SendPacketApp, RecvPacketApp, start_time_order
from qns.entity.cchannel.cchannel import ClassicChannel
from qns.entity.node import QNode
from qns.simulator.simulator import Simulator
from waxman_model import WaxmanTopology
from qns.network.topology.topo import ClassicTopology
from qns.network.route import DijkstraRouteAlgorithm
from create_request_ton import random_requests
from qns.utils import set_seed
from create_request_ton import time_accuracy as accuracy
import numpy as np
import matplotlib.pyplot as plt
import xlwt

# def drop_rate(length):   # 0.2db/km
#     return 1-np.power(10, -length/50000)


end_simu_time = 100
# q_length = 1000  # 与drop_rate有关
# c_length = 1000
# light_speed = 299791458
send_rate = 3000
s_time = 0
e_time = end_simu_time - 50
request_key = [(1000, 5000)]   #,(20000, 40000),(1000, 40000) 
times = [1, 5, 10, 20]
# s_request = 1000
# e_request = 5000
s_delay = 5
e_delay = end_simu_time - e_time    # float('inf')
square_size = 10000


def calculate_consume_key(nodes: list[QNode]):
    consume_key = 0
    for node in nodes:
        sendapp = node.get_apps(SendPacketApp).pop(0)
        consume_key += sendapp.consume_key
    return consume_key


for node_num in [50]:   #, 50, 250
    for (s_request, e_request) in request_key:
        recycle_times = 100
        end_to_end_key_rate_list = {}
        succ_serve_rate_list = {}
        consume_key_list = {}
        request_num_list = {}
        average_consume_list = {}
        for j in range(9, 10):
            end_to_end_key_rate_list[j] = []
            succ_serve_rate_list[j] = []
            consume_key_list[j] = []
            request_num_list[j] = []
            average_consume_list[j] = []
            for time in times:
                set_seed(1641801012+time+j)
                request_num = int(time * node_num)
                s = Simulator(0, end_simu_time, accuracy)
                topo = WaxmanTopology(nodes_number=node_num, size=square_size, alpha=1, beta=1)
                #   , qchannel_args={"delay": q_length / light_speed, "drop_rate": drop_rate(q_length)}, cchannel_args={"delay": c_length / light_speed}
                net = QuantumNetwork(topo=topo, route=DijkstraRouteAlgorithm(), classic_topo=ClassicTopology.All)
                #   print(net.qchannels)
                request_management = {}
                net_bb84rapps = {}
                net_bb84sapps = {}
                net_succ_request = {}
                net_reject_app_packet_symbol = {}
                for node in net.nodes:
                    net_bb84sapps[node.name] = []
                    net_bb84rapps[node.name] = []
                    net_succ_request[node.name] = []
                    net_reject_app_packet_symbol[node.name] = {}
                for qchannel in net.qchannels:
                    (src, dest) = qchannel.node_list
                    cchannel: ClassicChannel = src.get_cchannel(dest)
                    send = BB84SendApp(dest=dest, qchannel=qchannel, cchannel=cchannel, send_rate=send_rate)
                    recv = BB84RecvApp(src=src, qchannel=qchannel, cchannel=cchannel, send_rate=send_rate)
                    src.add_apps(send)
                    dest.add_apps(recv)
                    net_bb84sapps[src.name].append(send)
                    net_bb84sapps[dest.name].append(send)
                    net_bb84rapps[src.name].append(recv)
                    net_bb84rapps[dest.name].append(recv)
                net.build_route()
                random_requests(nodes=net.nodes, number=request_num, start_time=s_time, end_time=e_time, start_request=s_request,
                                end_request=e_request, start_delay=s_delay, end_delay=e_delay, allow_overlay=True)

                # print(net.requests)

                for node in net.nodes:
                    start_time_order(node.requests, 0, len(node.requests)-1)
                    sendre = SendPacketApp(net=net, node=node, bb84rapps=net_bb84rapps[node.name], bb84sapps=net_bb84sapps[node.name], reject_app_packet_symbol=net_reject_app_packet_symbol[node.name],
                                           request_management=request_management, request_list=node.requests)
                    recvre = RecvPacketApp(net=net, node=node, bb84_rapps=net_bb84rapps[node.name], bb84_sapps=net_bb84sapps[node.name], reject_app_packet_symbol=net_reject_app_packet_symbol[node.name],
                                           succ_request=net_succ_request[node.name])
                    node.add_apps(sendre)
                    node.add_apps(recvre)
                net.install(s)
                #   print(net.qchannels)
                s.run()
                #   succ_number = 0
                #   fail_number = 0
                #   for node in net.nodes:
                #       for i in net_succ_request[node.name]:
                #         print(i, i.attr)
                # for s in sendlist:
                #     print(len(s.succ_key_pool), s.current_pool)
                # for r in recvlist:
                #     print(len(r.succ_key_pool), r.current_pool)

                # print("successful!")
                # for node in net.nodes:
                #     print(node.name, len(net_succ_request[node.name]))
                #     succ_number += 1
                #     # print(net_succ_request[node.name])
                # print("failed!")
                # for node in net.nodes:
                #     print(node.name, len(net_fail_request[node.name]))
                #     fail_number += 1
                #     # print(net_fail_request[node.name])
                # print(succ_number, fail_number)
                request_num_list[j].append(request_num)
                #   node_num_list.append(node_num)
                succ_num = 0
                end_to_end_key = 0
                for node in net.nodes:
                    succ_num += len(net_succ_request[node.name])
                    for symbol in net_succ_request[node.name]:
                        re = request_management[symbol]
                        key_requirement = re.attr["key requirement"]
                        end_to_end_key += key_requirement
                #   succ_num = calculate_request_serve_rate(net.nodes)  # 计算请求服务率
                consume_key = calculate_consume_key(net.nodes)  # 传到一半失败的包会消耗一定密钥
                consume_key_list[j].append(consume_key)
                end_to_end_key_rate_list[j].append(end_to_end_key / consume_key)
                succ_serve_rate_list[j].append(succ_num / request_num)
                average_consume_list[j].append(end_to_end_key)
                #   consume_key = calculate_consume_key(net.nodes)  # 传到一半失败的包会消耗一定密钥
                #   consume_key_list.append(consume_key)
            f = open("centerize-data.txt", "a")
            f.write('\n')
            f.write(f"{node_num}-{s_request}-{e_request}-{j}")
            f.write('\n')
            f.write("request list:")
            f.write('\n')
            f.write(str(request_num_list[j]))
            f.write('\n')
            f.write("succ_serve_rate_list:")
            f.write('\n')
            f.write(str(succ_serve_rate_list[j]))
            f.write('\n')
            f.write("end_to_end_key_rate_list:")
            f.write('\n')
            f.write(str(end_to_end_key_rate_list[j]))
            f.write('\n')
            f.write("consume_key_list:")
            f.write('\n')
            f.write(str(consume_key_list[j]))
            f.write('\n')
            f.write("end_to_end_consume_key_list:")
            f.write('\n')
            f.write(str(average_consume_list[j]))
            excel = xlwt.Workbook(encoding='utf-8', style_compression=0)
            table = excel.add_sheet(f'{node_num}-{s_request}-{e_request}={j}-centerize', cell_overwrite_ok=True)
            classification = ['request_num', 'succ_serve_rate_list', 'end_to_end_key_rate_list', 'consume_key_list', 'end_to_end_consume_key_list']
            for i in range(0, 5):
                table.write(0, i+1, classification[i])
            for i in range(len(request_num_list[j])):
                k = 1
                table.write(i+1, k, request_num_list[j][i])
                k += 1
                table.write(i+1, k, succ_serve_rate_list[j][i])
                k += 1
                table.write(i+1, k, end_to_end_key_rate_list[j][i])
                k += 1
                table.write(i+1, k, consume_key_list[j][i])
                k += 1
                table.write(i+1, k, average_consume_list[j][i])
            excel.save(f'{node_num}-{s_request}-{e_request}-{j}-centerize.xlsx')
        request_num_list_final = []
        consume_key_list_final = []
        end_to_end_key_rate_list_final = []
        succ_serve_rate_list_final = []
        average_consume_list_final = []
        for k in range(0, len(times)):
            request_num_sum = 0
            consume_key_sum = 0
            end_to_end_key_rate_sum = 0
            succ_serve_rate_sum = 0
            average_consume_sum = 0
            for j in range(0, recycle_times):
                request_num_sum += request_num_list[j][k]
                consume_key_sum += consume_key_list[j][k]
                end_to_end_key_rate_sum += end_to_end_key_rate_list[j][k]
                succ_serve_rate_sum += succ_serve_rate_list[j][k]
                average_consume_sum += average_consume_list[j][k]
            request_num_list_final.append(request_num_sum / recycle_times)
            consume_key_list_final.append(consume_key_sum / recycle_times)
            end_to_end_key_rate_list_final.append(end_to_end_key_rate_sum / recycle_times)
            succ_serve_rate_list_final.append(succ_serve_rate_sum / recycle_times)
            average_consume_list_final.append(average_consume_sum / recycle_times)
        f = open("centerize-data.txt", "a")
        f.write('\n')
        f.write(f"{node_num}-{s_request}-{e_request}")
        f.write('\n')
        f.write("request list:")
        f.write('\n')
        f.write(str(request_num_list_final))
        f.write('\n')
        f.write("succ_serve_rate_list:")
        f.write('\n')
        f.write(str(succ_serve_rate_list_final))
        f.write('\n')
        f.write("end_to_end_key_rate_list:")
        f.write('\n')
        f.write(str(end_to_end_key_rate_list_final))
        f.write('\n')
        f.write("consume_key_list:")
        f.write('\n')
        f.write(str(consume_key_list_final))
        f.write('\n')
        f.write("end_to_end_consume_key_list:")
        f.write('\n')
        f.write(str(average_consume_list_final))
        excel = xlwt.Workbook(encoding='utf-8', style_compression=0)
        table = excel.add_sheet(f'{node_num}-{s_request}-{e_request}-centerize', cell_overwrite_ok=True)
        classification = ['request_num', 'succ_serve_rate_list', 'end_to_end_key_rate_list', 'consume_key_list', 'end_to_end_consume_key_list']
        for i in range(0, 5):
            table.write(0, i+1, classification[i])
        for i in range(len(request_num_list_final)):
            j = 1
            table.write(i+1, j, request_num_list_final[i])
            j += 1
            table.write(i+1, j, succ_serve_rate_list_final[i])
            j += 1
            table.write(i+1, j, end_to_end_key_rate_list_final[i])
            j += 1
            table.write(i+1, j, consume_key_list_final[i])
            j += 1
            table.write(i+1, j, average_consume_list_final[i])
        excel.save(f'{node_num}-{s_request}-{e_request}-centerize.xlsx')
        # plt.xticks(np.arange(0, 20*node_num+1, node_num))
        # plt.xlabel('request number')
        # plt.ylim((0, 1.1))
        # plt.tick_params(labelsize=8)
        # #   plt.ylabel('rate of serving successfully')
        # plt.yticks(np.arange(0, 1.1, 0.1))
        # plt.plot(request_num_list_final, succ_serve_rate_list_final, color='grey',
        #          marker='o', markersize=4, linewidth=2, markerfacecolor='gray',
        #          markeredgecolor='grey', markeredgewidth=2)
        # plt.legend(['rate of serving successfully'], loc='upper right')
        # #   plt.savefig('figures/20-800-100-myscheme-serve-rate.png', dpi=300)
        # plt.show()
        # plt.cla()
        # plt.xticks(np.arange(0, 20*node_num+1, node_num))
        # plt.xlabel('request number')
        # plt.ylim((0, 1.1))
        # plt.tick_params(labelsize=8)
        # #   plt.ylabel('rate of serving successfully')
        # plt.yticks(np.arange(0, 1.1, 0.1))
        # plt.plot(request_num_list_final, end_to_end_key_rate_list_final, color='red',
        #          marker='o', markersize=4, linewidth=2, markerfacecolor='red',
        #          markeredgecolor='red', markeredgewidth=2)
        # plt.legend(['rate of consuming keys'], loc='upper right')
        # #   plt.savefig('figures/20-800-100-myscheme-consume-rate.png', dpi=300)
        # plt.show()
        # plt.cla()
        # plt.xticks(np.arange(0, 20*node_num+1, node_num))
        # plt.xlabel('request number')
        # plt.tick_params(labelsize=8)
        # plt.plot(request_num_list_final, consume_key_list_final, color='blue',
        #          marker='o', markersize=4, linewidth=2, markerfacecolor='blue',
        #          markeredgecolor='blue', markeredgewidth=2)
        # plt.legend(['number of consumed keys'], loc='upper left')
        # #   plt.savefig('figures/20-800-100-myscheme-consume-key.png', dpi=300)
        # plt.show()
        # plt.cla()
        # plt.xticks(np.arange(0, 20*node_num+1, node_num))
        # plt.xlabel('request number')
        # plt.tick_params(labelsize=8)
        # plt.plot(request_num_list_final, average_consume_list_final, color='green',
        #          marker='o', markersize=4, linewidth=2, markerfacecolor='green',
        #          markeredgecolor='green', markeredgewidth=2)
        # plt.legend(['end_to_end_consume_key_list'], loc='upper left')
        # #   plt.savefig('figures/20-800-100-myscheme-average-consume-key.png', dpi=300)
        # plt.show()
