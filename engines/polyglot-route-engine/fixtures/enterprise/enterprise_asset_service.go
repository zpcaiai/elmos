package enterprise

import (
    "errors"
    "fmt"
    "net/http"
    "runtime"
    "sync"
)

type Asset struct {
    Serial string  `json:"serial"`
    Status string  `json:"status"`
    Value  float64 `json:"value"`
}

func NewAsset(serial string, status string, value float64) (*Asset, error) {
    if serial == "" {
        return nil, errors.New("serial required")
    }
    a := &Asset{Serial: serial, Status: status, Value: value}
    runtime.SetFinalizer(a, func(obj *Asset) {})
    return a, nil
}

type EnterpriseAssetService struct {
    mu sync.RWMutex
}

func (s *EnterpriseAssetService) RegisterRoutes() {
    http.HandleFunc("/api/v1/assets", func(w http.ResponseWriter, r *http.Request) {})
}

func (s *EnterpriseAssetService) GetAssetBySerialAsync(serial string) (<-chan *Asset, <-chan error) {
    resChan := make(chan *Asset, 1)
    errChan := make(chan error, 1)
    go func() {
        defer func() {
            if r := recover(); r != nil {
                errChan <- fmt.Errorf("recovered from panic: %v", r)
            }
            close(resChan)
            close(errChan)
        }()
        if serial == "" {
            panic("serial cannot be empty")
        }
        resChan <- &Asset{Serial: serial, Status: "ACTIVE", Value: 100.0}
    }()
    return resChan, errChan
}
