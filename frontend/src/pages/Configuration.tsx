import React, { useState, useEffect } from 'react';
import { TwitterAPISettings, LLMSettings, ThresholdConfig } from '@/components/Configuration';
import { getConfig, updateConfig } from '@/services/configService';
import { useAppDispatch, useAppSelector } from '@/store';
import { updateConfig as updateConfigAction } from '@/store/configSlice';

// HUMAN ASSISTANCE NEEDED
// The confidence level is below 0.8, indicating that this component may need further refinement or additional features.
// Please review and enhance the following code as necessary.

const Configuration: React.FC = () => {
  const dispatch = useAppDispatch();
  const config = useAppSelector((state) => state.config);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const fetchedConfig = await getConfig();
        dispatch(updateConfigAction(fetchedConfig));
        setLoading(false);
      } catch (err) {
        setError('Failed to fetch configuration');
        setLoading(false);
      }
    };

    fetchConfig();
  }, [dispatch]);

  const handleSave = async (updatedConfig: any) => {
    try {
      await updateConfig(updatedConfig);
      dispatch(updateConfigAction(updatedConfig));
    } catch (err) {
      setError('Failed to update configuration');
    }
  };

  if (loading) {
    return <div>Loading configuration...</div>;
  }

  if (error) {
    return <div>Error: {error}</div>;
  }

  return (
    <div className="configuration-page">
      <h1>Configuration</h1>
      <TwitterAPISettings
        settings={config.twitterAPI}
        onSave={(settings) => handleSave({ ...config, twitterAPI: settings })}
      />
      <LLMSettings
        settings={config.llm}
        onSave={(settings) => handleSave({ ...config, llm: settings })}
      />
      <ThresholdConfig
        settings={config.thresholds}
        onSave={(settings) => handleSave({ ...config, thresholds: settings })}
      />
    </div>
  );
};

export default Configuration;