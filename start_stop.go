package main

import (
	"bytes"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"strconv"
	"time"
)

const (
	apiBase      = "http://45.136.236.186:8080"
	defaultIdTag = "DEMO_IDTAG"
)

var httpClient = &http.Client{
	Timeout: 15 * time.Second,
	Transport: &http.Transport{
		DisableKeepAlives: true,
		DialContext: (&net.Dialer{
			Timeout:   5 * time.Second,
			KeepAlive: 0,
		}).DialContext,
		TLSHandshakeTimeout:   5 * time.Second,
		ExpectContinueTimeout: 0,
		IdleConnTimeout:       0,
		MaxIdleConns:          0,
	},
}

func doJSON(method, url, body string) (int, []byte, error) {
	req, err := http.NewRequest(method, url, bytes.NewBufferString(body))
	if err != nil {
		return 0, nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Connection", "close") // ปิดหลังจบ (ซ้ำกับ DisableKeepAlives)

	resp, err := httpClient.Do(req)
	if err != nil {
		return 0, nil, err
	}
	defer resp.Body.Close()

	b, _ := io.ReadAll(resp.Body)
	fmt.Printf("%s %s -> %d %s\n", method, url, resp.StatusCode, http.StatusText(resp.StatusCode))
	fmt.Println(string(b))
	return resp.StatusCode, b, nil
}

func startCharge(cpid string, connectorId int, idTag string) error {
	url := fmt.Sprintf("%s/api/v1/start", apiBase)
	jsonBody := fmt.Sprintf(`{"cpid":"%s","connectorId":%d,"idTag":"%s"}`, cpid, connectorId, idTag)
	_, _, err := doJSON("POST", url, jsonBody)
	return err
}

func stopCharge(cpid string, connectorId int) error {
	url := fmt.Sprintf("%s/api/v1/stop", apiBase)
	jsonBody := fmt.Sprintf(`{"cpid":"%s","connectorId":%d}`, cpid, connectorId)
	status, _, err := doJSON("POST", url, jsonBody)
	if err != nil {
		return err
	}
	if status == http.StatusNotFound {
		relURL := fmt.Sprintf("%s/api/v1/release", apiBase)
		relBody := fmt.Sprintf(`{"cpid":"%s","connectorId":%d}`, cpid, connectorId)
		_, _, err = doJSON("POST", relURL, relBody)
	}
	return err
}

func main() {
	if len(os.Args) < 3 {
		fmt.Println("usage:")
		fmt.Println("  go run start_stop.go start <cpid> <connectorId> [idTag]")
		fmt.Println("  go run start_stop.go stop  <cpid> <connectorId>")
		return
	}

	cmd := os.Args[1]

	switch cmd {
	case "start":
		if len(os.Args) < 4 {
			fmt.Println("usage: go run start_stop.go start <cpid> <connectorId> [idTag]")
			return
		}
		cpid := os.Args[2]
		connectorId, err := strconv.Atoi(os.Args[3])
		if err != nil {
			fmt.Println("Invalid connectorId:", err)
			return
		}
		idTag := defaultIdTag
		if len(os.Args) >= 5 {
			idTag = os.Args[4]
		}
		if err := startCharge(cpid, connectorId, idTag); err != nil {
			fmt.Println("Error starting charge:", err)
		}
	case "stop":
		if len(os.Args) < 4 {
			fmt.Println("usage: go run start_stop.go stop <cpid> <connectorId>")
			return
		}
		cpid := os.Args[2]
		connectorId, err := strconv.Atoi(os.Args[3])
		if err != nil {
			fmt.Println("Invalid connectorId:", err)
			return
		}
		if err := stopCharge(cpid, connectorId); err != nil {
			fmt.Println("Error stopping charge:", err)
		}
	default:
		fmt.Println("unknown cmd:", cmd)
		fmt.Println("usage:")
		fmt.Println("  go run start_stop.go start <cpid> <connectorId> [idTag]")
		fmt.Println("  go run start_stop.go stop  <cpid> <connectorId>")
	}
}
