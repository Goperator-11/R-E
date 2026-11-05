import hashlib
import hmac
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def varint(data,offset):
    assert offset<len(data)
    size=1<<(data[offset]>>6)
    assert offset+size<=len(data)
    value=int.from_bytes(data[offset:offset+size],"big")&((1<<(8*size-2))-1)
    return value,offset+size


def expand(secret,label,size):
    label=b"tls13 "+label
    info=size.to_bytes(2,"big")+bytes([len(label)])+label+b"\x00"
    out=part=b"";counter=1
    while len(out)<size:
        part=hmac.new(secret,part+info+bytes([counter]),hashlib.sha256).digest();out+=part;counter+=1
    return out[:size]


def keys(dcid):
    initial=hmac.new(bytes.fromhex("38762cf7f55934b34d179ae6a4c80cadccbb7f0a"),dcid,hashlib.sha256).digest()
    secret=expand(initial,b"client in",32)
    return dict(key=expand(secret,b"quic key",16),iv=expand(secret,b"quic iv",12),hp=expand(secret,b"quic hp",16))


def packets(data):
    start=0
    while start<len(data):
        if not data[start]&128:return
        typ=(data[start]>>4)&3;assert data[start+1:start+5]==b"\x00\x00\x00\x01" and typ!=3
        pos=start+5;n=data[pos];dcid=data[pos+1:pos+1+n];pos+=1+n
        n=data[pos];pos+=1+n
        if typ==0:
            n,pos=varint(data,pos);pos+=n
        n,pos=varint(data,pos);end=pos+n
        assert pos<end<=len(data)
        yield typ,start,pos,end,dcid
        start=end


def decrypt(data,start,pn_offset,end,key):
    sample=data[pn_offset+4:pn_offset+20];assert len(sample)==16
    enc=Cipher(algorithms.AES(key["hp"]),modes.ECB()).encryptor()
    mask=enc.update(sample)+enc.finalize()
    first=data[start]^(mask[0]&15);pn_size=(first&3)+1
    number=bytes(data[pn_offset+i]^mask[i+1] for i in range(pn_size));pn=int.from_bytes(number,"big")
    header=bytearray(data[start:pn_offset+pn_size]);header[0]=first;header[-pn_size:]=number
    nonce=bytes(a^b for a,b in zip(key["iv"],pn.to_bytes(12,"big")))
    plain=AESGCM(key["key"]).decrypt(nonce,data[pn_offset+pn_size:end],bytes(header))
    return pn,plain


def crypto_frames(plain):
    pos=0;result=[]
    while pos<len(plain):
        kind,pos=varint(plain,pos)
        if kind in (0,1):continue
        if kind in (2,3):
            _,pos=varint(plain,pos);_,pos=varint(plain,pos);count,pos=varint(plain,pos);_,pos=varint(plain,pos)
            for _ in range(count):_,pos=varint(plain,pos);_,pos=varint(plain,pos)
            if kind==3:
                for _ in range(3):_,pos=varint(plain,pos)
            continue
        if kind==6:
            offset,pos=varint(plain,pos);size,pos=varint(plain,pos);body=plain[pos:pos+size];assert len(body)==size
            result.append((offset,body));pos+=size;continue
        if kind in (28,29):
            _,pos=varint(plain,pos)
            if kind==28:_,pos=varint(plain,pos)
            size,pos=varint(plain,pos);pos+=size;assert pos<=len(plain);continue
        raise AssertionError(("unexpected Initial frame",kind))
    return result


def transport_parameters(hello):
    assert hello[0]==1 and len(hello)==4+int.from_bytes(hello[1:4],"big")
    pos=4+2+32;n=hello[pos];pos+=1+n
    n=int.from_bytes(hello[pos:pos+2],"big");pos+=2+n
    n=hello[pos];pos+=1+n
    n=int.from_bytes(hello[pos:pos+2],"big");pos+=2;assert pos+n==len(hello)
    values=None
    while pos<len(hello):
        kind=int.from_bytes(hello[pos:pos+2],"big");n=int.from_bytes(hello[pos+2:pos+4],"big");pos+=4;body=hello[pos:pos+n];pos+=n;assert len(body)==n
        if kind==57:
            assert values is None;values={};at=0
            while at<len(body):
                key,at=varint(body,at);n,at=varint(body,at);value=body[at:at+n];assert len(value)==n and key not in values;values[key]=value;at+=n
    assert values is not None
    return values


def inspect(wire,observation):
    key=None;pieces={};records=[]
    for event in wire:
        data=bytes.fromhex(event["wire_hex"])
        for typ,start,pos,end,dcid in packets(data):
            if typ!=0:continue
            if key is None:key=keys(dcid)
            pn,plain=decrypt(data,start,pos,end,key);frames=crypto_frames(plain)
            for offset,body in frames:
                for i,x in enumerate(body,offset):
                    if i in pieces:assert pieces[i]==x
                    pieces[i]=x
            ranges=[[offset,len(body)] for offset,body in frames]
            records.append(dict(pn=pn,crypto=ranges,packet_bytes=end-start,authenticated=True))
    assert pieces and len(pieces)==max(pieces)+1
    hello=bytes(pieces[i] for i in range(len(pieces)));params=transport_parameters(hello)
    qlog=[p for p in observation["packets"] if p["direction"]=="sent" and p["space"]=="initial"]
    for rec in records:
        assert any(p["pn"]==rec["pn"] and p["crypto"]==rec["crypto"] for p in qlog),(rec,qlog)
    return dict(client_hello_bytes=len(hello),client_hello_sha256=hashlib.sha256(hello).hexdigest(),authenticated_initial_packets=len(records),crypto_packets=sum(bool(r["crypto"]) for r in records),packets=records,parameter_ids=list(params),padding_bytes=len(params.get(9730,b"")),padding_present=9730 in params,padding_zero=params.get(9730,b"")==bytes(len(params.get(9730,b""))))
