import hashlib

from experiments.v33 import initial_inspect as wire


def integer(value,minimum=0):
    if type(value) is not int or value<minimum:
        raise ValueError("invalid trace integer")
    return value


def intervals(ranges,lengths=True):
    items=[]
    for pair in ranges:
        if len(pair)!=2:
            raise ValueError("invalid range pair")
        a=integer(pair[0])
        b=a+integer(pair[1],1) if lengths else integer(pair[1],a+1)
        items.append((a,b))
    result=[]
    for a,b in sorted(items):
        if result and a<=result[-1][1]:result[-1]=(result[-1][0],max(result[-1][1],b))
        else:result.append((a,b))
    return result


def length(ranges):
    return sum(b-a for a,b in ranges)


def overlap(left,right):
    return sum(max(0,min(b,d)-max(a,c)) for a,b in left for c,d in right)


def client_wire(events):
    key=None
    records=[]
    for event in events:
        if event["direction"]!="c2s" or event.get("parity") or "wire_hex" not in event:
            continue
        data=bytes.fromhex(event["wire_hex"])
        if not event.get("initial",False):continue
        if len(data)!=event["bytes"]:
            raise ValueError("wire length mismatch")
        for typ,start,pos,end,dcid in wire.packets(data):
            if typ!=0:continue
            if key is None:key=wire.keys(dcid)
            pn,plain=wire.decrypt(data,start,pos,end,key)
            frames=wire.crypto_frames(plain)
            records.append(dict(pn=pn,crypto=[[offset,len(body)] for offset,body in frames],
                crc32c=event["crc32c"],datagram_bytes=len(data),packet_bytes=end-start,
                payload_sha256=hashlib.sha256(plain).hexdigest()))
    return records


def analyze(observation,first_k,events):
    integer(first_k)
    if observation["truncated"]:
        raise ValueError("truncated qlog observation")
    packets=observation["packets"]
    previous=-1
    sent={}
    for packet in packets:
        at=integer(packet["at_ns"])
        if at<previous:raise ValueError("packet callbacks are not time ordered")
        previous=at
        integer(packet["pn"])
        integer(packet["bytes"],1)
        intervals(packet["crypto"])
        if packet["direction"] not in ("sent","received"):raise ValueError("invalid packet direction")
        if packet["direction"]=="sent":
            key=packet["space"],packet["pn"]
            if key in sent:raise ValueError("duplicate sent packet number in one space")
            sent[key]=packet
    authenticated=client_wire(events)
    for raw in authenticated:
        item=sent.get(("initial",raw["pn"]))
        if item is None or item["crypto"]!=raw["crypto"]:
            raise ValueError("authenticated CRYPTO does not match qlog")
        if item["crc32c"]!=raw["crc32c"] or item["bytes"]!=raw["packet_bytes"]:
            raise ValueError("authenticated datagram identity mismatch")
    ptos=[integer(x) for x in observation["pto_at_ns"]]
    if ptos!=sorted(ptos):raise ValueError("PTO callbacks are not time ordered")
    first_received=min((p["at_ns"] for p in packets if p["direction"]=="received"),default=None)
    first_ack=min((p["at_ns"] for p in packets if p["direction"]=="received" and p["space"]=="initial" and p["ack_ranges"]),default=None)
    covered=[]
    acknowledged=set()
    rows=[]
    ack_rows=[]
    for packet in packets:
        if packet["direction"]=="received" and packet["space"]=="initial":
            newly=[]
            for low,high in packet["ack_ranges"]:
                integer(low);integer(high,low)
                if high-low>100000:raise ValueError("ACK range exceeds diagnostic bound")
                for pn in range(low,high+1):
                    owner=sent.get(("initial",pn))
                    if owner is None or owner["at_ns"]>packet["at_ns"]:
                        raise ValueError("ACK refers to an unseen or future Initial")
                    if pn not in acknowledged:newly.append(pn)
                    acknowledged.add(pn)
            if packet["ack_ranges"]:
                ack_rows.append(dict(at_ns=packet["at_ns"],pn=packet["pn"],ranges=packet["ack_ranges"],newly_acked=sorted(newly)))
        if packet["direction"]!="sent" or packet["space"]!="initial" or not packet["crypto"]:continue
        ranges=intervals(packet["crypto"])
        repeated=overlap(ranges,covered)
        acked=intervals([pair for pn in acknowledged for pair in sent["initial",pn]["crypto"]])
        before=[x for x in ptos if x<=packet["at_ns"]]
        matching=[x for x in events if x["direction"]=="c2s" and x["crc32c"]==packet["crc32c"] and x["bytes"]==packet["bytes"]]
        if len(matching)>1 and any(x.get("wire_hex")!=matching[0].get("wire_hex") for x in matching):
            raise ValueError("CRC metadata has conflicting wire values")
        rows.append(dict(pn=packet["pn"],at_ns=packet["at_ns"],ranges=packet["crypto"],crypto_bytes=length(ranges),
            repeated_bytes=repeated,new_bytes=length(ranges)-repeated,acked_overlap_bytes=overlap(ranges,acked),
            latest_preceding_pto_ns=before[-1] if before else None,
            before_any_received=first_received is None or packet["at_ns"]<first_received,
            before_any_initial_ack=first_ack is None or packet["at_ns"]<first_ack,
            relay_matches=len(matching),relay_dropped=sum(x["dropped"] for x in matching),
            authenticated_matches=sum(x["pn"]==packet["pn"] for x in authenticated)))
        covered=intervals(covered+ranges,lengths=False)
    pto_rows=[]
    for at in ptos:
        before=[p for p in rows if p["at_ns"]<=at]
        pto_rows.append(dict(at_ns=at,last_crypto_send_ns=before[-1]["at_ns"] if before else None,
            since_last_crypto_send_ms=(at-before[-1]["at_ns"])/1e6 if before else None,
            before_any_received=first_received is None or at<first_received,
            before_any_initial_ack=first_ack is None or at<first_ack))
    return dict(crypto_packets=rows,initial_ack_packets=ack_rows,pto_callbacks=pto_rows,
        first_bundle_k=first_k,first_bundle_ranges=[x["ranges"] for x in rows[:first_k]],
        unique_crypto_bytes=length(covered),repeated_crypto_packets=sum(x["repeated_bytes"]>0 for x in rows),
        repeated_crypto_bytes=sum(x["repeated_bytes"] for x in rows),
        acked_overlap_bytes=sum(x["acked_overlap_bytes"] for x in rows),
        authenticated_initial_packets=len(authenticated),authenticated_crypto_packets=sum(bool(x["crypto"]) for x in authenticated),
        relay_unmatched_crypto_packets=sum(x["relay_matches"]==0 for x in rows),
        qlog_initial_ack_packets=len(ack_rows),raw_wire_available=any("wire_hex" in x for x in events),
        server_ack_authenticated=False,pto_causality="precedence_only",actual_socket_send_time_observed=False)
