package main

import (
	"os"
	"path/filepath"
	"testing"
)

const preserveTestArtifactsEnv = "QAMP_PRESERVE_TEST_ARTIFACTS"

func preservedTempDir(t *testing.T) string {
	t.Helper()
	if os.Getenv(preserveTestArtifactsEnv) != "1" {
		return t.TempDir()
	}
	home, err := os.UserHomeDir()
	if err != nil {
		t.Fatal(err)
	}
	base := filepath.Join(home, "quicbed_gen33", "test_artifacts")
	if err := os.MkdirAll(base, 0700); err != nil {
		t.Fatal(err)
	}
	dir, err := os.MkdirTemp(base, "test-")
	if err != nil {
		t.Fatal(err)
	}
	t.Logf("preserved test artifacts in %s", dir)
	return dir
}

func TestPreservedTempDirIsRemovedUnlessRequested(t *testing.T) {
	home := t.TempDir()
	t.Setenv("HOME", home)
	t.Setenv(preserveTestArtifactsEnv, "")
	var removed string
	t.Run("default", func(t *testing.T) {
		removed = preservedTempDir(t)
		if err := os.WriteFile(filepath.Join(removed, "cache.json"), []byte("{}"), 0600); err != nil {
			t.Fatal(err)
		}
	})
	if _, err := os.Stat(removed); !os.IsNotExist(err) {
		t.Fatalf("default test artifact directory survived the test: %v", err)
	}
	if _, err := os.Stat(filepath.Join(home, "quicbed_gen33")); !os.IsNotExist(err) {
		t.Fatalf("default test run wrote under HOME/quicbed_gen33: %v", err)
	}
	t.Setenv(preserveTestArtifactsEnv, "1")
	var kept string
	t.Run("preserve", func(t *testing.T) { kept = preservedTempDir(t) })
	if filepath.Dir(kept) != filepath.Join(home, "quicbed_gen33", "test_artifacts") {
		t.Fatalf("preserved directory %s", kept)
	}
	if info, err := os.Stat(kept); err != nil || !info.IsDir() {
		t.Fatalf("requested preservation was not kept: %v", err)
	}
}
