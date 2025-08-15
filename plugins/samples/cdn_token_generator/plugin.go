// plugin.go - CDN Token Generator for Media CDN

package main

import (
    "crypto/ed25519"
    "encoding/base64"
    "encoding/json"
    "fmt"
    "strconv"
    "time"

    "github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm"
    "github.com/proxy-wasm/proxy-wasm-go-sdk/proxywasm/types"
)

// PluginConfig contiene la configuración del plugin
type PluginConfig struct {
    PrivateKey       string `json:"privateKey"`       // Clave Ed25519 codificada en base64
    KeyName          string `json:"keyName"`          // Nombre de la clave para Media CDN
    ExpirySeconds    int    `json:"expirySeconds"`    // Tiempo de validez en segundos
    UrlHeaderName    string `json:"urlHeaderName"`    // Cabecera que contiene la URL a firmar
    OutputHeaderName string `json:"outputHeaderName"` // Cabecera donde colocar la URL firmada
}

// Configuración por defecto
var defaultConfig = PluginConfig{
    PrivateKey:       "mO9BH59zXD0rJjYGZ4ult7GrwZc/EoX4VpNcwWPp0JQ=",
    KeyName:          "test-key",
    ExpirySeconds:    3600, // 1 hora
    UrlHeaderName:    "X-Original-URL",
    OutputHeaderName: "X-Signed-URL",
}

var config PluginConfig

func main() {
    proxywasm.SetVMContext(&vmContext{})
}

type vmContext struct{}

func (*vmContext) OnVMStart(vmConfigurationSize int) types.OnVMStartStatus {
    return types.OnVMStartStatusOK
}

func (*vmContext) NewPluginContext(contextID uint32) types.PluginContext {
    return &pluginContext{}
}

type pluginContext struct{}

func (ctx *pluginContext) OnPluginStart(pluginConfigurationSize int) types.OnPluginStartStatus {
    config = defaultConfig
    
    data, err := proxywasm.GetPluginConfiguration()
    if err == nil && len(data) > 0 {
        proxywasm.LogInfo("Parsing plugin configuration")
        if err := json.Unmarshal(data, &config); err != nil {
            proxywasm.LogError("failed to unmarshal config: " + err.Error())
        }
    } else {
        proxywasm.LogInfo("Using default configuration")
    }

    proxywasm.LogInfo("Plugin initialized with key name: " + config.KeyName)
    return types.OnPluginStartStatusOK
}

func (ctx *pluginContext) OnPluginDone() bool {
    return true
}

func (ctx *pluginContext) NewHttpContext(contextID uint32) types.HttpContext {
    return &httpContext{}
}

func (ctx *pluginContext) NewTcpContext(contextID uint32) types.TcpContext {
    return nil
}

func (ctx *pluginContext) OnTick() {
}

func (ctx *pluginContext) OnQueueReady(queueID uint32) {
}

type httpContext struct {
    types.DefaultHttpContext
}

func (ctx *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
    originalURL, err := proxywasm.GetHttpRequestHeader(config.UrlHeaderName)
    if err != nil || originalURL == "" {
        proxywasm.LogDebug("URL header not found or empty: " + config.UrlHeaderName)
        return types.ActionContinue
    }

    proxywasm.LogInfo("Generating signed URL for: " + originalURL)

    signedURL, err := generateSignedURL(originalURL)
    if err != nil {
        proxywasm.LogError("Failed to generate signed URL: " + err.Error())
        return types.ActionContinue
    }

    if err := proxywasm.AddHttpRequestHeader(config.OutputHeaderName, signedURL); err != nil {
        proxywasm.LogError("Failed to add signed URL header")
    } else {
        proxywasm.LogInfo("Added signed URL to " + config.OutputHeaderName + " header")
    }

    return types.ActionContinue
}

func generateSignedURL(originalURL string) (string, error) {
    privateKeyBytes, err := base64.StdEncoding.DecodeString(config.PrivateKey)
    if err != nil {
        return "", fmt.Errorf("invalid private key: %v", err)
    }

    if len(privateKeyBytes) != ed25519.PrivateKeySize {
        return "", fmt.Errorf("invalid key size: expected %d bytes", ed25519.PrivateKeySize)
    }

    expiryTime := time.Now().Unix() + int64(config.ExpirySeconds)
    expiryString := strconv.FormatInt(expiryTime, 10)

    urlPrefix := base64.URLEncoding.WithPadding(base64.NoPadding).EncodeToString([]byte(originalURL))
    stringToSign := fmt.Sprintf("URLPrefix=%s&Expires=%s&KeyName=%s",
        urlPrefix, expiryString, config.KeyName)

    signature := ed25519.Sign(ed25519.PrivateKey(privateKeyBytes), []byte(stringToSign))
    signatureBase64 := base64.URLEncoding.WithPadding(base64.NoPadding).EncodeToString(signature)

    signedURL := fmt.Sprintf("%s?URLPrefix=%s&Expires=%s&KeyName=%s&Signature=%s",
        originalURL, urlPrefix, expiryString, config.KeyName, signatureBase64)

    return signedURL, nil
}
