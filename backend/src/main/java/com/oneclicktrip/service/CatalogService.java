package com.oneclicktrip.service;

import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.oneclicktrip.common.BusinessException;
import com.oneclicktrip.entity.*;
import com.oneclicktrip.mapper.*;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class CatalogService {
    private final CityMapper cityMapper;
    private final ScenicSpotMapper scenicSpotMapper;
    private final FoodMapper foodMapper;
    private final HotelMapper hotelMapper;
    private final TripTemplateMapper tripTemplateMapper;

    public CatalogService(
            CityMapper cityMapper,
            ScenicSpotMapper scenicSpotMapper,
            FoodMapper foodMapper,
            HotelMapper hotelMapper,
            TripTemplateMapper tripTemplateMapper
    ) {
        this.cityMapper = cityMapper;
        this.scenicSpotMapper = scenicSpotMapper;
        this.foodMapper = foodMapper;
        this.hotelMapper = hotelMapper;
        this.tripTemplateMapper = tripTemplateMapper;
    }

    public List<City> listCities() {
        return cityMapper.selectList(Wrappers.<City>lambdaQuery()
                .eq(City::getStatus, 1)
                .orderByAsc(City::getSortOrder)
                .orderByDesc(City::getId));
    }

    public City getCity(Long id) {
        City city = cityMapper.selectById(id);
        if (city == null || city.getStatus() == null || city.getStatus() != 1) {
            throw new BusinessException("城市不存在或未启用");
        }
        return city;
    }

    public List<ScenicSpot> listSpots(Long cityId) {
        getCity(cityId);
        return scenicSpotMapper.selectList(Wrappers.<ScenicSpot>lambdaQuery()
                .eq(ScenicSpot::getCityId, cityId)
                .eq(ScenicSpot::getStatus, 1)
                .orderByAsc(ScenicSpot::getSortOrder)
                .orderByDesc(ScenicSpot::getRating));
    }

    public List<Food> listFoods(Long cityId) {
        getCity(cityId);
        return foodMapper.selectList(Wrappers.<Food>lambdaQuery()
                .eq(Food::getCityId, cityId)
                .eq(Food::getStatus, 1)
                .orderByAsc(Food::getSortOrder)
                .orderByAsc(Food::getId));
    }

    public List<Hotel> listHotels(Long cityId) {
        getCity(cityId);
        return hotelMapper.selectList(Wrappers.<Hotel>lambdaQuery()
                .eq(Hotel::getCityId, cityId)
                .eq(Hotel::getStatus, 1)
                .orderByAsc(Hotel::getAvgPrice)
                .orderByDesc(Hotel::getRating));
    }

    public List<TripTemplate> listTemplates(Long cityId) {
        return tripTemplateMapper.selectList(Wrappers.<TripTemplate>lambdaQuery()
                .eq(cityId != null, TripTemplate::getCityId, cityId)
                .eq(TripTemplate::getStatus, 1)
                .orderByAsc(TripTemplate::getDays)
                .orderByAsc(TripTemplate::getId));
    }
}

