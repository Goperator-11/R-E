#!/bin/bash
SRC=/mnt/c/dev/pq_afec_gen3/experiments/quicbed
cd "$SRC"
for f in $(ls *.go build.sh go.mod go.sum 2>/dev/null | LC_ALL=C sort); do
	printf '%s %s\n' "$f" "$(sha256sum "$f" | cut -d' ' -f1)"
done | sha256sum | cut -d' ' -f1
echo "recorded: $(cat $HOME/quicbed_g3/bin/qamp.srcsha 2>/dev/null)"
ls -la $HOME/quicbed_g3/bin/ /tmp/qamp_g3/g3/ /tmp/qamp_g3/g2/ 2>&1
sha256sum $HOME/quicbed_g3/bin/qamp /tmp/qamp_g3/g3/qamp /tmp/qamp_g3/g2/qamp $HOME/quicbed/bin/qamp 2>&1
cat $HOME/quicbed_g3/bin/qamp.sha256
diff <(sed 's/\r$//' $SRC/qamp.go) $HOME/quicbed_g3/cmd/qamp/main.go && echo "build tree main.go == current qamp.go"
diff <(sed 's/\r$//' $SRC/qamp_lead_test.go) $HOME/quicbed_g3/cmd/qamp/qamp_lead_test.go && echo "build tree lead test == current"
grep -c '^--- PASS' $HOME/quicbed_g3/bin/go_test.txt
mount | grep ' /tmp ' || echo "no /tmp mount line"
