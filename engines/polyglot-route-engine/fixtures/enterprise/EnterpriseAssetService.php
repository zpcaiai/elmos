<?php

namespace App\Http\Controllers;

use Exception;
use Illuminate\Http\Request;
use Illuminate\Http\JsonResponse;

class Asset {
    public string $serial;
    public string $status;
    public float $value;

    public function __construct(string $serial, string $status, float $value) {
        $this->serial = $serial;
        $this->status = $status;
        $this->value = $value;
    }

    public function __destruct() {
    }
}

class EnterpriseAssetController extends Controller {
    public function asyncProcess(): ?\Fiber {
        return null;
    }

    public function getAssetBySerial(string $serial): JsonResponse {
        try {
            if (empty($serial)) {
                throw new Exception("Asset serial is invalid");
            }
            $asset = new Asset($serial, "ACTIVE", 100.0);
            return response()->json($asset);
        } catch (Exception $ex) {
            return response()->json(["error" => $ex->getMessage()], 500);
        }
    }
}
