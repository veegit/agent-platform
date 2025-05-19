"""
Skill parameter validation for the Agentic Platform.
"""

import logging
import json
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, ValidationError, create_model

from shared.models.skill import Skill, SkillParameter, ParameterType

logger = logging.getLogger(__name__)


class ValidationResult(BaseModel):
    """Result of parameter validation."""
    
    valid: bool
    errors: Optional[Dict[str, List[str]]] = None
    validated_params: Optional[Dict[str, Any]] = None


class SkillValidator:
    """Validator for skill parameters."""
    
    def __init__(self):
        """Initialize the skill validator."""
        pass

    def validate_parameters(self, skill: Skill, parameters: Dict[str, Any]) -> ValidationResult:
        """Validate parameters against a skill's parameter definitions.
        
        Args:
            skill: The skill with parameter definitions.
            parameters: The parameters to validate.
            
        Returns:
            ValidationResult: Result of validation.
        """
        errors: Dict[str, List[str]] = {}
        validated_params = {}
        
        # Check for required parameters
        for param in skill.parameters:
            if param.required and param.name not in parameters:
                if param.name not in errors:
                    errors[param.name] = []
                errors[param.name].append(f"Required parameter '{param.name}' is missing")
        
        # Validate parameter types and values
        for param in skill.parameters:
            param_name = param.name
            
            # Skip validation if parameter is not provided and not required
            if param_name not in parameters:
                if param.default is not None:
                    # Use default value
                    validated_params[param_name] = param.default
                continue
            
            param_value = parameters[param_name]
            validation_errors = self._validate_parameter_value(param, param_value)
            
            if validation_errors:
                if param_name not in errors:
                    errors[param_name] = []
                errors[param_name].extend(validation_errors)
            else:
                # Add validated parameter
                validated_params[param_name] = param_value
        
        # Check for unknown parameters
        known_params = {param.name for param in skill.parameters}
        unknown_params = set(parameters.keys()) - known_params
        
        for param_name in unknown_params:
            if param_name not in errors:
                errors[param_name] = []
            errors[param_name].append(f"Unknown parameter '{param_name}'")
        
        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors if errors else None,
            validated_params=validated_params
        )
    
    def _validate_parameter_value(self, param: SkillParameter, value: Any) -> List[str]:
        """Validate a parameter value against its definition.
        
        Args:
            param: The parameter definition.
            value: The parameter value.
            
        Returns:
            List[str]: List of validation errors (empty if valid).
        """
        errors = []
        
        # Check if value is None
        if value is None:
            if param.required:
                errors.append(f"Required parameter '{param.name}' cannot be None")
            return errors
        
        # Check enum values
        if param.enum is not None and value not in param.enum:
            enum_values = ", ".join(str(v) for v in param.enum)
            errors.append(f"Value '{value}' for parameter '{param.name}' must be one of: {enum_values}")
        
        # Type validation
        if param.type == ParameterType.STRING:
            if not isinstance(value, str):
                errors.append(f"Parameter '{param.name}' must be a string")
        
        elif param.type == ParameterType.INTEGER:
            if not isinstance(value, int) or isinstance(value, bool):
                errors.append(f"Parameter '{param.name}' must be an integer")
        
        elif param.type == ParameterType.FLOAT:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(f"Parameter '{param.name}' must be a number")
        
        elif param.type == ParameterType.BOOLEAN:
            if not isinstance(value, bool):
                errors.append(f"Parameter '{param.name}' must be a boolean")
        
        elif param.type == ParameterType.ARRAY:
            if not isinstance(value, list):
                errors.append(f"Parameter '{param.name}' must be an array")
        
        elif param.type == ParameterType.OBJECT:
            if not isinstance(value, dict):
                errors.append(f"Parameter '{param.name}' must be an object")
        
        return errors
    
    def create_pydantic_model(self, skill: Skill) -> Tuple[Any, ValidationResult]:
        """Create a Pydantic model from skill parameters.
        
        This allows for using Pydantic's validation system for more complex validation.
        
        Args:
            skill: The skill with parameter definitions.
            
        Returns:
            Tuple[Any, ValidationResult]: A tuple containing the Pydantic model class
                and a validation result for the model creation.
        """
        field_definitions = {}
        validation_errors = {}
        
        for param in skill.parameters:
            try:
                # Map parameter type to Python type
                python_type = self._map_param_type_to_python(param.type)
                
                # Add field definition
                field_info = {}
                
                if param.description:
                    field_info["description"] = param.description
                
                if not param.required:
                    field_info["default"] = param.default
                
                if param.enum:
                    field_info["enum"] = param.enum
                
                field_definitions[param.name] = (python_type, field_info)
                
            except Exception as e:
                if param.name not in validation_errors:
                    validation_errors[param.name] = []
                validation_errors[param.name].append(str(e))
        
        # Create model if no errors
        if not validation_errors:
            try:
                model = create_model(
                    f"{skill.name}Parameters",
                    **field_definitions
                )
                return model, ValidationResult(valid=True, validated_params={})
            except Exception as e:
                logger.error(f"Failed to create Pydantic model for skill {skill.name}: {e}")
                return None, ValidationResult(
                    valid=False,
                    errors={"model": [f"Failed to create validation model: {str(e)}"]}
                )
        else:
            return None, ValidationResult(valid=False, errors=validation_errors)
    
    def _map_param_type_to_python(self, param_type: ParameterType) -> type:
        """Map a parameter type to a Python type.
        
        Args:
            param_type: The parameter type.
            
        Returns:
            type: The corresponding Python type.
            
        Raises:
            ValueError: If the parameter type is unknown.
        """
        mapping = {
            ParameterType.STRING: str,
            ParameterType.INTEGER: int,
            ParameterType.FLOAT: float,
            ParameterType.BOOLEAN: bool,
            ParameterType.ARRAY: list,
            ParameterType.OBJECT: dict
        }
        
        if param_type not in mapping:
            raise ValueError(f"Unknown parameter type: {param_type}")
        
        return mapping[param_type]
    
    def validate_with_pydantic(self, model: Any, parameters: Dict[str, Any]) -> ValidationResult:
        """Validate parameters using a Pydantic model.
        
        Args:
            model: The Pydantic model to use for validation.
            parameters: The parameters to validate.
            
        Returns:
            ValidationResult: Result of validation.
        """
        try:
            validated = model(**parameters)
            return ValidationResult(
                valid=True,
                validated_params=validated.dict()
            )
        except ValidationError as e:
            errors = {}
            for error in e.errors():
                field = ".".join(str(loc) for loc in error["loc"])
                if field not in errors:
                    errors[field] = []
                errors[field].append(error["msg"])
            
            return ValidationResult(
                valid=False,
                errors=errors
            )
        except Exception as e:
            return ValidationResult(
                valid=False,
                errors={"validation": [str(e)]}
            )