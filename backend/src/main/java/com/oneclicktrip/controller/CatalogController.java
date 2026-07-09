package com.oneclicktrip.controller;

import com.oneclicktrip.common.ApiResponse;
import com.oneclicktrip.entity.*;
import com.oneclicktrip.service.CatalogService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api")
public class CatalogController {
    private final CatalogService catalogService;

    public CatalogController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @GetMapping("/cities")
    public ApiResponse<List<City>> cities() {
        return ApiResponse.ok(catalogService.listCities());
    }

    @GetMapping("/cities/{id}")
    public ApiResponse<City> city(@PathVariable Long id) {
        return ApiResponse.ok(catalogService.getCity(id));
    }

    @GetMapping("/cities/{id}/spots")
    public ApiResponse<List<ScenicSpot>> spots(@PathVariable Long id) {
        return ApiResponse.ok(catalogService.listSpots(id));
    }

    @GetMapping("/cities/{id}/foods")
    public ApiResponse<List<Food>> foods(@PathVariable Long id) {
        return ApiResponse.ok(catalogService.listFoods(id));
    }

    @GetMapping("/cities/{id}/hotels")
    public ApiResponse<List<Hotel>> hotels(@PathVariable Long id) {
        return ApiResponse.ok(catalogService.listHotels(id));
    }

    @GetMapping("/trip-templates")
    public ApiResponse<List<TripTemplate>> templates(@RequestParam(required = false) Long cityId) {
        return ApiResponse.ok(catalogService.listTemplates(cityId));
    }
}

