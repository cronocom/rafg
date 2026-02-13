"""
═══════════════════════════════════════════════════════════
RAGF Safety Validators
Capa 3: Independent Validators (Aviation Domain)
═══════════════════════════════════════════════════════════

Implementaciones concretas de validadores para aviación.
Cada uno verifica una regulación FAA específica.
"""

import structlog
from gateway.validators.base_validator import BaseValidator
from shared.models import ActionPrimitive

logger = structlog.get_logger()


class FuelReserveValidator(BaseValidator):
    """
    Valida FAA 14 CFR §91.151: Fuel requirements for VFR conditions
    
    Regla: Reroute NO puede reducir fuel por debajo de:
    - VFR Día: 30 minutos de reserva
    - VFR Noche: 45 minutos de reserva
    """
    
    def __init__(self):
        super().__init__(name="FuelReserveValidator", timeout_ms=50)
        
        # Constantes (estos valores vendrían de config en producción)
        self.vfr_day_reserve_minutes = 30
        self.vfr_night_reserve_minutes = 45
        self.avg_burn_rate_kg_per_min = 45.0  # Típico para A320
    
    async def _validate_impl(
        self,
        action: ActionPrimitive
    ) -> tuple[str, str, str | None]:
        """
        Valida fuel para reroute_flight.
        
        Lógica simplificada para MVA:
        - Obtener new_distance de parameters
        - Calcular fuel requerido
        - Comparar con fuel actual (simulado)
        """
        if action.verb != "reroute_flight":
            # Este validador solo aplica a reroutes
            return ("PASS", "Not applicable to this action", None)
        
        params = action.parameters
        
        # Simular datos del vuelo (en producción vendría de sistema real)
        current_fuel_kg = params.get("current_fuel_kg", 5000)
        new_distance_nm = params.get("new_distance_nm", 0)
        is_night = params.get("is_night", False)
        
        # Calcular fuel requerido
        reserve_minutes = (
            self.vfr_night_reserve_minutes if is_night 
            else self.vfr_day_reserve_minutes
        )
        
        # Conversión simplificada: 1 nm ≈ 1 minuto de vuelo crucero
        flight_time_minutes = new_distance_nm
        total_fuel_required = (
            (flight_time_minutes + reserve_minutes) * self.avg_burn_rate_kg_per_min
        )
        
        if current_fuel_kg < total_fuel_required:
            return (
                "FAIL",
                f"Insufficient fuel: have {current_fuel_kg}kg, need {total_fuel_required}kg "
                f"(includes {reserve_minutes}min reserve per FAA 14 CFR §91.151)",
                "FAA-14-CFR-91.151"
            )
        
        logger.info(
            "fuel_validation_passed",
            current=current_fuel_kg,
            required=total_fuel_required,
            margin_kg=current_fuel_kg - total_fuel_required
        )
        
        return (
            "PASS",
            f"Fuel adequate: {current_fuel_kg}kg available, {total_fuel_required}kg required",
            None
        )


class CrewRestValidator(BaseValidator):
    """
    Valida FAA 14 CFR §121.471: Flight time limitations and rest requirements
    
    Regla: Reroute NO puede extender duty time más allá de:
    - Máximo 9 horas de duty period
    - Mínimo 10 horas de descanso consecutivo
    """
    
    def __init__(self):
        super().__init__(name="CrewRestValidator", timeout_ms=50)
        self.max_duty_period_minutes = 540  # 9 horas
    
    async def _validate_impl(
        self,
        action: ActionPrimitive
    ) -> tuple[str, str, str | None]:
        """
        Valida crew rest para reroute_flight.
        """
        if action.verb != "reroute_flight":
            return ("PASS", "Not applicable to this action", None)
        
        params = action.parameters
        
        # Simular datos de crew (en producción vendría de sistema real)
        current_duty_minutes = params.get("current_duty_minutes", 300)  # 5h
        additional_flight_minutes = params.get("additional_flight_minutes", 0)
        
        total_duty = current_duty_minutes + additional_flight_minutes
        
        if total_duty > self.max_duty_period_minutes:
            return (
                "FAIL",
                f"Crew duty time would exceed limit: {total_duty} minutes > "
                f"{self.max_duty_period_minutes} minutes (FAA 14 CFR §121.471)",
                "FAA-14-CFR-121.471"
            )
        
        logger.info(
            "crew_rest_validation_passed",
            total_duty=total_duty,
            limit=self.max_duty_period_minutes,
            margin_minutes=self.max_duty_period_minutes - total_duty
        )
        
        return (
            "PASS",
            f"Crew duty within limits: {total_duty}/{self.max_duty_period_minutes} minutes",
            None
        )


class AirspaceValidator(BaseValidator):
    """
    Valida FAA 14 CFR §91.119: Minimum safe altitudes
    
    Regla: Altitude NO puede violar mínimos de seguridad:
    - Sobre áreas congestionadas: 1,000 ft sobre obstáculo más alto
    - Sobre áreas abiertas: 500 ft sobre superficie
    """
    
    def __init__(self):
        super().__init__(name="AirspaceValidator", timeout_ms=50)
        
        # Altitudes mínimas por tipo de terreno (simplificado)
        self.min_altitudes = {
            "congested": 1000,  # ft AGL
            "open": 500,
            "mountainous": 2000
        }
    
    async def _validate_impl(
        self,
        action: ActionPrimitive
    ) -> tuple[str, str, str | None]:
        """
        Valida altitude para adjust_altitude.
        """
        if action.verb != "adjust_altitude":
            return ("PASS", "Not applicable to this action", None)
        
        params = action.parameters
        
        # Simular datos de vuelo
        new_altitude_ft = params.get("new_altitude_ft", 10000)
        terrain_type = params.get("terrain_type", "open")
        terrain_elevation_ft = params.get("terrain_elevation_ft", 0)
        
        min_altitude_agl = self.min_altitudes.get(terrain_type, 500)
        min_altitude_msl = terrain_elevation_ft + min_altitude_agl
        
        if new_altitude_ft < min_altitude_msl:
            return (
                "FAIL",
                f"Altitude {new_altitude_ft}ft below minimum safe altitude "
                f"{min_altitude_msl}ft MSL for {terrain_type} terrain "
                f"(FAA 14 CFR §91.119)",
                "FAA-14-CFR-91.119"
            )
        
        logger.info(
            "airspace_validation_passed",
            new_altitude=new_altitude_ft,
            min_altitude=min_altitude_msl,
            terrain=terrain_type
        )
        
        return (
            "PASS",
            f"Altitude safe: {new_altitude_ft}ft above minimum {min_altitude_msl}ft",
            None
        )


# Registry de validadores disponibles
VALIDATOR_REGISTRY = {
    "FuelReserveValidator": FuelReserveValidator,
    "CrewRestValidator": CrewRestValidator,
    "AirspaceValidator": AirspaceValidator,
}


def get_validator(name: str) -> BaseValidator:
    """
    Factory function para instanciar validadores por nombre.
    
    Args:
        name: Nombre del validador (ej: "FuelReserveValidator")
    
    Returns:
        Instancia del validador
    
    Raises:
        KeyError si el validador no existe
    """
    validator_class = VALIDATOR_REGISTRY.get(name)
    if not validator_class:
        raise KeyError(f"Validator '{name}' not found in registry")
    
    return validator_class()
