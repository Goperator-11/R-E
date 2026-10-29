#!/bin/bash
G3=$HOME/quicbed_g3/bin/qamp
G2=$HOME/quicbed/bin/qamp
sha256sum "$G3" "$G2"
"$G3" -mode selftest > /dev/null 2> "$HOME/quicbed_g3/_review/st_g3.txt"; echo "g3 rc $?"
"$G2" -mode selftest > /dev/null 2> "$HOME/quicbed_g3/_review/st_g2.txt"; echo "g2 rc $?"
for t in g3 g2; do
	echo "$t ok $(grep -c '^ok' $HOME/quicbed_g3/_review/st_$t.txt) FAIL $(grep -c '^FAIL' $HOME/quicbed_g3/_review/st_$t.txt)"
done
diff <(grep -E '^(ok|FAIL)' $HOME/quicbed_g3/_review/st_g2.txt | sed 's/[0-9.]\+//g') <(grep -E '^(ok|FAIL)' $HOME/quicbed_g3/_review/st_g3.txt | sed 's/[0-9.]\+//g') && echo "same check names"
for args in "-layout v3 -fec fec -m 3 -lead 4" "-layout v3 -m 3 -lead 3" "-layout v2 -fec fec -m 3 -lead 1" "-layout v3 -fec buf -m 3 -lead 1" "-layout v3 -fec fec -m 16 -lead 1" "-layout v4 -fec fec -m 3"; do
	timeout 5 "$G3" -mode client -addr 127.0.0.1:9 -n 1 $args > /dev/null 2>&1; echo "rc $? for: $args"
done
